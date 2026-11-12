import React, { useEffect, useState } from 'react';
import ForgeReconciler, { Tab, TabList, TabPanel, Tabs } from '@forge/react';
import { CoverageView } from './CoverageView';
import { InventoryView } from './InventoryView';
import { SettingsView } from './SettingsView';
import { fetchJiraConnection } from './lib/forgeApi';

// Mirrors frontend/src/App.tsx: two views behind tabs, and a best-effort
// lookup of the connected Jira site so Jira keys can render as real links.
const App = () => {
  const [siteUrl, setSiteUrl] = useState(null);

  useEffect(() => {
    fetchJiraConnection()
      .then((status) => setSiteUrl(status.connected ? status.site_url : null))
      .catch(() => setSiteUrl(null));
  }, []);

  return (
    <Tabs id="traceability-tabs">
      <TabList>
        <Tab>Test Inventory</Tab>
        <Tab>Requirement Coverage</Tab>
        <Tab>Settings</Tab>
      </TabList>
      <TabPanel>
        <InventoryView siteUrl={siteUrl} />
      </TabPanel>
      <TabPanel>
        <CoverageView siteUrl={siteUrl} />
      </TabPanel>
      <TabPanel>
        <SettingsView />
      </TabPanel>
    </Tabs>
  );
};

ForgeReconciler.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
