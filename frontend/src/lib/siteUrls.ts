/** Host links are independent of the sign-in provider. */
export function siteUrls(location: Pick<Location, 'hostname' | 'protocol' | 'port'>) {
  const { hostname, protocol, port } = location
  const local =
    hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')
  if (local) {
    const suffix = port ? `:${port}` : ''
    return {
      marketing: `${protocol}//localhost${suffix}`,
      app: `${protocol}//app.localhost${suffix}`,
    }
  }
  const domain = hostname.startsWith('app.') ? hostname.slice(4) : hostname
  return { marketing: `https://${domain}`, app: `https://app.${domain}` }
}
