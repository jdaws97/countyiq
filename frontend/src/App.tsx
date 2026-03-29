import { BrowserRouter, Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'
import MapView from './pages/MapView'
import MunicipalityList from './pages/MunicipalityList'
import OpsHealth from './pages/OpsHealth'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/map" element={<MapView />} />
        <Route path="/municipalities" element={<MunicipalityList />} />
        <Route path="/ops/health" element={<OpsHealth />} />
      </Routes>
    </BrowserRouter>
  )
}
