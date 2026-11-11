import React, { useEffect, useState } from 'react';
import ForgeReconciler, { Tab, TabList, TabPanel, Tabs, Text } from '@forge/react';
import { InventoryView } from './InventoryView';
import { fetchJiraConnection } from './lib/forgeApi';

// Mirrors frontend/src/App.tsx: two views behind tabs, and a best-effort
// lookup of the connected Jira site so Jira keys can render as real links.
// The Coverage tab is filled in by issues #31/#32.
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
      </TabList>
      <TabPanel>
        <InventoryView siteUrl={siteUrl} />
      </TabPanel>
      <TabPanel>
        <Text>Requirement Coverage is coming in the next step (issues #31/#32).</Text>
      </TabPanel>
    </Tabs>
  );
};

ForgeReconciler.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
