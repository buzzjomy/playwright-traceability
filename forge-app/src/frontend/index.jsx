import React, { useEffect, useState } from 'react';
import ForgeReconciler, { Text } from '@forge/react';
import { requestRemote } from '@forge/bridge';

// Walking skeleton (issue #28): proves the whole chain - this UI Kit panel
// -> Forge Remote -> FastAPI backend on Fly.io -> response -> render - works
// end to end before the real Inventory/Coverage views are ported (Milestone 8).
const App = () => {
  const [result, setResult] = useState('Loading...');

  useEffect(() => {
    requestRemote('traceability-backend', {
      path: '/api/jira/connection',
      method: 'GET',
    })
      .then(async (response) => {
        const body = await response.text();
        setResult(`HTTP ${response.status}: ${body}`);
      })
      .catch((error) => setResult(`Error: ${error}`));
  }, []);

  return <Text>{result}</Text>;
};

ForgeReconciler.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
