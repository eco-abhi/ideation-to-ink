import { useState } from "react";
import { PaperList } from "./pages/PaperList";
import { PaperDetail } from "./pages/PaperDetail";

function App() {
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 24px 48px" }}>
      <h1 style={{ fontSize: 18, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: 0.2 }}>
        research-pipeline dashboard
      </h1>
      {selectedPaperId ? (
        <PaperDetail paperId={selectedPaperId} onBack={() => setSelectedPaperId(null)} />
      ) : (
        <PaperList onSelect={setSelectedPaperId} />
      )}
    </div>
  );
}

export default App;
