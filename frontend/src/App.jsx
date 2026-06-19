import { BrowserRouter, Routes, Route } from "react-router-dom";
import Navbar     from "./components/Navbar";
import ChatPage   from "./pages/ChatPage";
import MitrePage  from "./pages/MitrePage";
import CertPage   from "./pages/CertPage";
import ThreatPage from "./pages/ThreatPage";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-950 text-white">
        <Navbar />
        <Routes>
          <Route path="/"        element={<ChatPage />}   />
          <Route path="/mitre"   element={<MitrePage />}  />
          <Route path="/cert"    element={<CertPage />}   />
          <Route path="/threats" element={<ThreatPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
