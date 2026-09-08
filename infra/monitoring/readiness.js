import http from "k6/http";
import { check } from "k6";
import secrets from "k6/secrets";

export const options = {
  thresholds: { checks: ["rate==1"] },
};

export default async function () {
  const clientId = await secrets.get("countyiq-health-client-id");
  const clientSecret = await secrets.get("countyiq-health-client-secret");
  const response = http.get("https://app.countyiq.net/api/ready", {
    headers: {
      "CF-Access-Client-Id": clientId,
      "CF-Access-Client-Secret": clientSecret,
    },
    redirects: 0,
    timeout: "10s",
  });
  check(response, {
    "readiness returns HTTP 200": (result) => result.status === 200,
    "database-backed readiness is ok": (result) => {
      try {
        return result.json("status") === "ok";
      } catch {
        return false;
      }
    },
  });
}
