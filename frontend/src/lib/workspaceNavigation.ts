export type WorkspaceIcon =
  'activity' | 'building' | 'compare' | 'home' | 'map' | 'pin' | 'properties' | 'watch'

type NavigationItem = {
  icon: WorkspaceIcon
  label: string
  to: string
  aliases?: string[]
}

type NavigationGroup = {
  label: string
  collapsed?: boolean
  items: NavigationItem[]
}

export const WORKSPACE_NAVIGATION: NavigationGroup[] = [
  {
    label: 'Site research',
    items: [
      { to: '/sites', label: 'Site inquiries', icon: 'home' },
      { to: '/map', label: 'Map', icon: 'map' },
      { to: '/radar', label: 'Properties', icon: 'properties' },
      { to: '/municipalities', label: 'Municipalities', icon: 'pin' },
    ],
  },
  {
    label: 'My workspace',
    items: [
      { to: '/watch', label: 'Following', icon: 'watch' },
      { to: '/compare', label: 'Compare', icon: 'compare' },
      { to: '/my-work', label: 'My work', icon: 'building' },
    ],
  },
  {
    label: 'County intelligence',
    collapsed: true,
    items: [
      { to: '/overview', aliases: ['/app'], label: 'County overview', icon: 'activity' },
      { to: '/feed', label: 'Activity', icon: 'activity' },
      {
        to: '/intelligence',
        aliases: ['/opportunities'],
        label: 'Emerging intelligence',
        icon: 'activity',
      },
      { to: '/organizations', label: 'Organizations', icon: 'building' },
    ],
  },
]

function matchesRoute(pathname: string, route: string): boolean {
  return pathname === route || pathname.startsWith(`${route}/`)
}

export function navigationItemActive(pathname: string, item: NavigationItem): boolean {
  return [item.to, ...(item.aliases ?? [])].some((route) => matchesRoute(pathname, route))
}

export function workspacePage(pathname: string): { title: string; context: string } {
  const details = [
    { path: '/sites/new', title: 'New inquiry', group: 'Site research' },
    { path: '/property', title: 'Property investigation', group: 'Site research' },
    { path: '/owner', title: 'Organization profile', group: 'County intelligence' },
    { path: '/entity', title: 'Organization profile', group: 'County intelligence' },
    { path: '/project', title: 'Project case file', group: 'County intelligence' },
    { path: '/ops/health', title: 'System health', group: 'Operations' },
  ]
  const detail = details.find((item) => matchesRoute(pathname, item.path))
  if (detail) {
    return { title: detail.title, context: `${detail.group} / ${detail.title}` }
  }
  for (const group of WORKSPACE_NAVIGATION) {
    const item = group.items.find((entry) => navigationItemActive(pathname, entry))
    if (item) {
      return { title: item.label, context: `${group.label} / ${item.label}` }
    }
  }
  if (pathname === '/') {
    return { title: 'Site inquiries', context: 'Site research / Site inquiries' }
  }
  if (pathname === '/search') {
    return { title: 'Search', context: 'Search CountyIQ' }
  }
  return { title: 'CountyIQ', context: 'CountyIQ' }
}
