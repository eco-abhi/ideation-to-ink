import { useState } from "react";
import { PaperList } from "./pages/PaperList";
import { PaperDetail } from "./pages/PaperDetail";

function App() {
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 24, fontFamily: "system-ui, sans-serif" }}>
      <h1 style={{ fontSize: 20 }}>research-pipeline dashboard</h1>
      {selectedPaperId ? (
        <PaperDetail paperId={selectedPaperId} onBack={() => setSelectedPaperId(null)} />
      ) : (
        <PaperList onSelect={setSelectedPaperId} />
      )}
    </div>
  );
}

export default App;
