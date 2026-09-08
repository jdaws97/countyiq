use anyhow::{anyhow, bail, Context, Result};
use futures_util::{stream, StreamExt};
use reqwest::Client;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::env;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tokio::time::sleep;

const MAX_RETRIES: usize = 3;

#[derive(Clone, Debug)]
struct Config {
    url: String,
    where_clause: String,
    out_fields: String,
    pidn_field: String,
    batch_size: usize,
    concurrency: usize,
    timeout_seconds: u64,
    max_pages: Option<usize>,
    return_geometry: bool,
    archive: Option<PathBuf>,
}

#[derive(Default, Debug, PartialEq, Eq)]
struct Fingerprint {
    count: u64,
    missing: u64,
    xor: u128,
    sum: u128,
}

impl Fingerprint {
    fn add(&mut self, pidn: Option<String>) {
        let Some(pidn) = pidn else {
            self.missing += 1;
            return;
        };

        let digest = Sha256::digest(pidn.as_bytes());
        let value = u128::from_be_bytes(digest[..16].try_into().expect("SHA-256 prefix"));
        self.count += 1;
        self.xor ^= value;
        self.sum = self.sum.wrapping_add(value);
    }
}

fn usage() -> &'static str {
    "Usage: countyiq-arcgis-bench --url URL [options]\n\
     \nOptions:\n\
       --where SQL             ArcGIS where clause (default: 1=1)\n\
       --out-fields FIELDS     ArcGIS fields (default: *)\n\
       --pidn-field FIELD      Identity field to fingerprint (default: PIDN)\n\
       --batch-size N          Features per request (default: 2000)\n\
       --concurrency N         Maximum in-flight page requests (default: 4)\n\
       --timeout-seconds N     Per-request timeout (default: 120)\n\
       --max-pages N           Stop after N pages for a bounded smoke test\n\
       --no-geometry           Do not request geometry\n\
       --archive PATH          Stream each feature as NDJSON\n\
       --help                  Show this help"
}

fn parse_args() -> Result<Config> {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        println!("{}", usage());
        std::process::exit(0);
    }

    let mut url: Option<String> = None;
    let mut where_clause = "1=1".to_owned();
    let mut out_fields = "*".to_owned();
    let mut pidn_field = "PIDN".to_owned();
    let mut batch_size = 2_000usize;
    let mut concurrency = 4usize;
    let mut timeout_seconds = 120u64;
    let mut max_pages: Option<usize> = None;
    let mut return_geometry = true;
    let mut archive: Option<PathBuf> = None;

    let mut index = 0usize;
    while index < args.len() {
        let key = &args[index];
        if key == "--no-geometry" {
            return_geometry = false;
            index += 1;
            continue;
        }

        let value = args
            .get(index + 1)
            .ok_or_else(|| anyhow!("missing value for {key}"))?;
        match key.as_str() {
            "--url" => url = Some(value.clone()),
            "--where" => where_clause = value.clone(),
            "--out-fields" => out_fields = value.clone(),
            "--pidn-field" => pidn_field = value.clone(),
            "--batch-size" => batch_size = value.parse().context("invalid --batch-size")?,
            "--concurrency" => concurrency = value.parse().context("invalid --concurrency")?,
            "--timeout-seconds" => {
                timeout_seconds = value.parse().context("invalid --timeout-seconds")?
            }
            "--max-pages" => max_pages = Some(value.parse().context("invalid --max-pages")?),
            "--archive" => archive = Some(PathBuf::from(value)),
            _ => bail!("unknown argument {key}\n\n{}", usage()),
        }
        index += 2;
    }

    if batch_size == 0 {
        bail!("--batch-size must be greater than zero");
    }
    if concurrency == 0 {
        bail!("--concurrency must be greater than zero");
    }
    if max_pages == Some(0) {
        bail!("--max-pages must be greater than zero");
    }

    Ok(Config {
        url: url.ok_or_else(|| anyhow!("--url is required\n\n{}", usage()))?,
        where_clause,
        out_fields,
        pidn_field,
        batch_size,
        concurrency,
        timeout_seconds,
        max_pages,
        return_geometry,
        archive,
    })
}

async fn fetch_json(
    client: &Client,
    url: &str,
    params: &[(String, String)],
) -> Result<(usize, Value)> {
    let mut last_error = "request did not run".to_owned();

    for attempt in 0..=MAX_RETRIES {
        match client.get(url).query(params).send().await {
            Ok(response) => {
                let status = response.status();
                match response.bytes().await {
                    Ok(body) => {
                        if status.is_client_error() {
                            bail!(
                                "ArcGIS returned non-retryable HTTP {}: {}",
                                status,
                                String::from_utf8_lossy(&body)
                            );
                        }
                        if !status.is_success() {
                            last_error = format!(
                                "ArcGIS returned HTTP {}: {}",
                                status,
                                String::from_utf8_lossy(&body)
                            );
                        } else {
                            match serde_json::from_slice::<Value>(&body) {
                                Ok(payload) if payload.get("error").is_none() => {
                                    return Ok((body.len(), payload));
                                }
                                Ok(payload) => {
                                    last_error =
                                        format!("ArcGIS error payload: {}", payload["error"]);
                                }
                                Err(error) => {
                                    last_error = format!("invalid ArcGIS JSON: {error}");
                                }
                            }
                        }
                    }
                    Err(error) => {
                        last_error = format!("reading response body from {url}: {error}");
                    }
                }
            }
            Err(error) => {
                last_error = format!("ArcGIS request failed: {error}");
            }
        }

        if attempt < MAX_RETRIES {
            sleep(Duration::from_millis(500 * (1u64 << attempt))).await;
        }
    }

    bail!(
        "request failed after {} attempts: {last_error}",
        MAX_RETRIES + 1
    )
}

async fn feature_count(client: &Client, query_url: &str, config: &Config) -> Result<usize> {
    let params = vec![
        ("where".to_owned(), config.where_clause.clone()),
        ("returnCountOnly".to_owned(), "true".to_owned()),
        ("f".to_owned(), "json".to_owned()),
    ];
    let (_, payload) = fetch_json(client, query_url, &params).await?;
    payload["count"]
        .as_u64()
        .map(|count| count as usize)
        .ok_or_else(|| anyhow!("count response did not contain an integer count: {payload}"))
}

async fn fetch_page(
    client: &Client,
    query_url: &str,
    config: &Config,
    offset: usize,
) -> Result<(usize, usize, Value)> {
    let params = vec![
        ("where".to_owned(), config.where_clause.clone()),
        ("outFields".to_owned(), config.out_fields.clone()),
        ("outSR".to_owned(), "4326".to_owned()),
        ("f".to_owned(), "json".to_owned()),
        (
            "resultRecordCount".to_owned(),
            config.batch_size.to_string(),
        ),
        ("resultOffset".to_owned(), offset.to_string()),
        (
            "returnGeometry".to_owned(),
            config.return_geometry.to_string(),
        ),
    ];
    let (response_bytes, payload) = fetch_json(client, query_url, &params).await?;
    Ok((offset, response_bytes, payload))
}

fn pidn_value(feature: &Value, field: &str) -> Option<String> {
    let value = feature.get("attributes")?.get(field)?;
    match value {
        Value::Null => None,
        Value::String(text) => Some(text.clone()),
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(boolean) => Some(boolean.to_string()),
        other => Some(other.to_string()),
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let config = parse_args()?;
    let query_url = format!("{}/query", config.url.trim_end_matches('/'));
    let client = Client::builder()
        .timeout(Duration::from_secs(config.timeout_seconds))
        .user_agent("CountyIQ ArcGIS ingestion benchmark/0.1")
        .build()
        .context("building HTTP client")?;

    let started = Instant::now();
    let expected_total = feature_count(&client, &query_url, &config).await?;
    let total_pages = expected_total.div_ceil(config.batch_size);
    let selected_pages = config.max_pages.unwrap_or(total_pages).min(total_pages);
    let offsets: Vec<usize> = (0..selected_pages)
        .map(|page| page * config.batch_size)
        .collect();

    let requests = stream::iter(offsets.into_iter().map(|offset| {
        let client = client.clone();
        let query_url = query_url.clone();
        let config = config.clone();
        async move { fetch_page(&client, &query_url, &config, offset).await }
    }))
    .buffer_unordered(config.concurrency);
    futures_util::pin_mut!(requests);

    let mut fingerprint = Fingerprint::default();
    let mut page_count = 0usize;
    let mut feature_count = 0usize;
    let mut response_bytes = 0usize;
    let mut archive = config
        .archive
        .as_ref()
        .map(|path| File::create(path).map(BufWriter::new))
        .transpose()
        .context("creating NDJSON archive")?;

    while let Some(page) = requests.next().await {
        let (offset, bytes, payload) = page?;
        let features = payload["features"]
            .as_array()
            .ok_or_else(|| anyhow!("page at offset {offset} did not contain a features array"))?;

        for feature in features {
            fingerprint.add(pidn_value(feature, &config.pidn_field));
            if let Some(writer) = archive.as_mut() {
                serde_json::to_writer(&mut *writer, feature)?;
                writer.write_all(b"\n")?;
            }
        }

        feature_count += features.len();
        response_bytes += bytes;
        page_count += 1;
    }

    if let Some(writer) = archive.as_mut() {
        writer.flush()?;
    }

    let complete = config.max_pages.is_none() && feature_count == expected_total;
    if config.max_pages.is_none() && feature_count != expected_total {
        bail!("full run returned {feature_count} features but ArcGIS reported {expected_total}");
    }

    println!(
        "{}",
        serde_json::to_string(&json!({
            "worker": "rust-bounded-parallel",
            "expected_total": expected_total,
            "feature_count": feature_count,
            "fingerprinted_count": fingerprint.count,
            "pidn_missing": fingerprint.missing,
            "pidn_xor": format!("{:032x}", fingerprint.xor),
            "pidn_sum": format!("{:032x}", fingerprint.sum),
            "pages": page_count,
            "response_bytes": response_bytes,
            "batch_size": config.batch_size,
            "concurrency": config.concurrency,
            "return_geometry": config.return_geometry,
            "complete": complete,
            "elapsed_seconds": started.elapsed().as_secs_f64(),
        }))?
    );

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::Fingerprint;

    #[test]
    fn fingerprint_is_order_independent_and_duplicate_sensitive() {
        let mut first = Fingerprint::default();
        first.add(Some("A".to_owned()));
        first.add(Some("B".to_owned()));

        let mut reversed = Fingerprint::default();
        reversed.add(Some("B".to_owned()));
        reversed.add(Some("A".to_owned()));
        assert_eq!(first, reversed);

        reversed.add(Some("A".to_owned()));
        assert_ne!(first, reversed);
    }

    #[test]
    fn fingerprint_counts_missing_identity() {
        let mut fingerprint = Fingerprint::default();
        fingerprint.add(None);
        assert_eq!(fingerprint.count, 0);
        assert_eq!(fingerprint.missing, 1);
    }
}
