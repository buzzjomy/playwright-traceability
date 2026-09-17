import { useEffect, useState } from 'react';
import './App.css';
import { CoverageView } from './CoverageView';
import { fetchJiraConnection } from './api';
import { InventoryView } from './InventoryView';

type Tab = 'inventory' | 'coverage';

const TAB_LABELS: Record<Tab, string> = {
  inventory: 'Test Inventory',
  coverage: 'Requirement Coverage',
};

function App() {
  const [tab, setTab] = useState<Tab>('inventory');
  const [siteUrl, setSiteUrl] = useState<string | null>(null);

  useEffect(() => {
    // Best-effort: if there's no Jira connection configured yet, jira
    // keys just render as plain text instead of links - not a hard error.
    fetchJiraConnection()
      .then((status) => setSiteUrl(status.connected ? status.site_url : null))
      .catch(() => setSiteUrl(null));
  }, []);

  return (
    <main className="page">
      <h1>{TAB_LABELS[tab]}</h1>

      <nav className="tabs">
        {(Object.keys(TAB_LABELS) as Tab[]).map((t) => (
          <button key={t} className={t === tab ? 'tab tab-active' : 'tab'} onClick={() => setTab(t)}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </nav>

      {tab === 'inventory' ? <InventoryView siteUrl={siteUrl} /> : <CoverageView siteUrl={siteUrl} />}
    </main>
  );
}

export default App;
