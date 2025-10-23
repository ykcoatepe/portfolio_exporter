import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Nav from "./components/Nav";
import PSD from "./pages/PSD";

export default function App(): JSX.Element {
  return (
    <BrowserRouter>
      <Nav />
      <Routes>
        <Route path="/psd" element={<PSD />} />
        <Route path="/" element={<Navigate to="/psd" replace />} />
        <Route path="*" element={<Navigate to="/psd" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
