import { lazy } from 'react'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import RouteFrame, { RouteError } from './components/RouteFrame'

const Organizations = lazy(() => import('./pages/Organizations'))
const WorkspaceHome = lazy(() => import('./pages/WorkspaceHome'))
const MapView = lazy(() => import('./pages/MapView'))
const PropertyDetail = lazy(() => import('./pages/PropertyDetail'))
const OwnerProfile = lazy(() => import('./pages/OwnerProfile'))
const DevelopmentRadar = lazy(() => import('./pages/DevelopmentRadar'))
const SearchResults = lazy(() => import('./pages/SearchResults'))
const OpsHealth = lazy(() => import('./pages/OpsHealth'))
const CountyFeed = lazy(() => import('./pages/CountyFeed'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const ProjectCaseFile = lazy(() => import('./pages/ProjectCaseFile'))
const ParcelCompare = lazy(() => import('./pages/ParcelCompare'))
const MunicipalityList = lazy(() => import('./pages/MunicipalityList'))
const MunicipalityDetail = lazy(() => import('./pages/MunicipalityDetail'))
const EmergingIntelligence = lazy(() => import('./pages/EmergingIntelligence'))
const SiteInquiries = lazy(() => import('./pages/SiteInquiries'))

const children = [
  { index: true, element: <Navigate replace to="/sites" /> },
  { path: 'sites', element: <SiteInquiries /> },
  { path: 'sites/:id', element: <SiteInquiries /> },
  { path: 'overview', element: <WorkspaceHome /> },
  { path: 'organizations', element: <Organizations /> },
  { path: 'app', element: <WorkspaceHome /> },
  { path: 'map', element: <MapView /> },
  { path: 'municipalities', element: <MunicipalityList /> },
  { path: 'municipalities/:name', element: <MunicipalityDetail /> },
  { path: 'delinquent', element: <Navigate replace to="/feed" /> },
  { path: 'licenses', element: <Navigate replace to="/search" /> },
  { path: 'projects', element: <Navigate replace to="/feed" /> },
  { path: 'project/:key', element: <ProjectCaseFile /> },
  { path: 'property/:pidn', element: <PropertyDetail /> },
  { path: 'owner/:id', element: <OwnerProfile /> },
  { path: 'entity/:id', element: <OwnerProfile /> },
  { path: 'distressed', element: <Navigate replace to="/feed" /> },
  { path: 'assemblage', element: <Navigate replace to="/radar" /> },
  { path: 'radar', element: <DevelopmentRadar /> },
  { path: 'search', element: <SearchResults /> },
  { path: 'ops/health', element: <OpsHealth /> },
  { path: 'feed', element: <CountyFeed /> },
  { path: 'watch', element: <Watchlist /> },
  { path: 'compare', element: <ParcelCompare /> },
  { path: 'intelligence', element: <EmergingIntelligence /> },
  { path: 'intelligence/:caseKey', element: <EmergingIntelligence /> },
  { path: 'opportunities', element: <EmergingIntelligence /> },
  { path: 'my-work', element: <EmergingIntelligence /> },
]

const router = createBrowserRouter([
  {
    path: '/',
    element: <RouteFrame />,
    errorElement: <RouteError />,
    children,
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
