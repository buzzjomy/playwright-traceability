import React from 'react';
import ForgeReconciler, { Tab, TabList, TabPanel, Tabs, useProductContext } from '@forge/react';
import { CoverageView } from './CoverageView';
import { InventoryView } from './InventoryView';
import { SettingsView } from './SettingsView';

// Mirrors frontend/src/App.tsx: views behind tabs. The Jira site URL (to render
// keys as real links) comes straight from Forge's own context - no backend call.
const App = () => {
  const context = useProductContext();
  const siteUrl = context?.siteUrl ?? null;

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
