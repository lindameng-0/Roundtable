import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "./components/ui/sonner";
import "./App.css";
import SetupPage from "./pages/SetupPage";
import ReadingPage from "./pages/ReadingPage";
import ReportPage from "./pages/ReportPage";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<SetupPage />} />
          <Route path="/read/:manuscriptId" element={<ReadingPage />} />
          <Route path="/report/:manuscriptId" element={<ReportPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </div>
  );
}

export default App;
