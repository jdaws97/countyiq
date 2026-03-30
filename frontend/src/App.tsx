import { BrowserRouter, Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'
import MapView from './pages/MapView'
import MunicipalityList from './pages/MunicipalityList'
import DelinquentOwners from './pages/DelinquentOwners'
import LicenseBrowser from './pages/LicenseBrowser'
import ProjectList from './pages/ProjectList'
import SearchResults from './pages/SearchResults'
import OpsHealth from './pages/OpsHealth'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/map" element={<MapView />} />
        <Route path="/municipalities" element={<MunicipalityList />} />
        <Route path="/delinquent" element={<DelinquentOwners />} />
        <Route path="/licenses" element={<LicenseBrowser />} />
        <Route path="/projects" element={<ProjectList />} />
        <Route path="/search" element={<SearchResults />} />
        <Route path="/ops/health" element={<OpsHealth />} />
      </Routes>
    </BrowserRouter>
  )
}
