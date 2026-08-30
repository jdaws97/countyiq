import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'

const MapView = lazy(() => import('./pages/MapView'))
const MunicipalityList = lazy(() => import('./pages/MunicipalityList'))
const MunicipalityDetail = lazy(() => import('./pages/MunicipalityDetail'))
const DelinquentOwners = lazy(() => import('./pages/DelinquentOwners'))
const LicenseBrowser = lazy(() => import('./pages/LicenseBrowser'))
const ProjectList = lazy(() => import('./pages/ProjectList'))
const PropertyDetail = lazy(() => import('./pages/PropertyDetail'))
const OwnerProfile = lazy(() => import('./pages/OwnerProfile'))
const DistressedParcels = lazy(() => import('./pages/DistressedParcels'))
const Assemblage = lazy(() => import('./pages/Assemblage'))
const DevelopmentRadar = lazy(() => import('./pages/DevelopmentRadar'))
const SearchResults = lazy(() => import('./pages/SearchResults'))
const OpsHealth = lazy(() => import('./pages/OpsHealth'))
const CountyFeed = lazy(() => import('./pages/CountyFeed'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const ProjectCaseFile = lazy(() => import('./pages/ProjectCaseFile'))
const restrictedDistressEnabled = import.meta.env.VITE_ENABLE_RESTRICTED_DISTRESS === 'true'

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<div className="route-loading">Loading CountyIQ…</div>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/map" element={<MapView />} />
          <Route path="/municipalities" element={<MunicipalityList />} />
          <Route path="/municipalities/:name" element={<MunicipalityDetail />} />
          {restrictedDistressEnabled && <Route path="/delinquent" element={<DelinquentOwners />} />}
          <Route path="/licenses" element={<LicenseBrowser />} />
          <Route path="/projects" element={<ProjectList />} />
          <Route path="/project/:key" element={<ProjectCaseFile />} />
          <Route path="/property/:pidn" element={<PropertyDetail />} />
          <Route path="/owner/:id" element={<OwnerProfile />} />
          <Route path="/entity/:id" element={<OwnerProfile />} />
          {restrictedDistressEnabled && <Route path="/distressed" element={<DistressedParcels />} />}
          {restrictedDistressEnabled && <Route path="/assemblage" element={<Assemblage />} />}
          <Route path="/radar" element={<DevelopmentRadar />} />
          <Route path="/search" element={<SearchResults />} />
          <Route path="/ops/health" element={<OpsHealth />} />
          <Route path="/feed" element={<CountyFeed />} />
          <Route path="/watch" element={<Watchlist />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
