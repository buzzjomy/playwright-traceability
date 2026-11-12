import React, { useEffect, useState } from 'react';
import { Button, CodeBlock, Heading, SectionMessage, Spinner, Stack, Text, Textfield } from '@forge/react';
import { createIngestKey, fetchTenant, spikeSystemToken } from './lib/forgeApi';
import { uploadCommand } from './lib/ciSnippet';

// Where an installation connects its CI (issue #42): it shows this
// installation's id and lets the customer generate the key their CI uses to
// upload test results. The key is returned exactly once by the backend, so
// it's held in component state only and gone on reload.

export const SettingsView = () => {
  const [tenant, setTenant] = useState(null);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [newKey, setNewKey] = useState(null);
  // SPIKE (issue #41) - throwaway state for the system-token probe.
  const [spike, setSpike] = useState(null);
  const [spiking, setSpiking] = useState(false);

  useEffect(() => {
    fetchTenant()
      .then(setTenant)
      .catch((err) => setError(err.message));
  }, []);

  const generate = () => {
    setGenerating(true);
    setError(null);
    createIngestKey()
      .then((result) => {
        setNewKey(result.ingest_key);
        setTenant((current) => ({ ...current, has_ingest_key: true }));
      })
      .catch((err) => setError(err.message))
      .finally(() => setGenerating(false));
  };

  const runSpike = () => {
    setSpiking(true);
    setSpike(null);
    spikeSystemToken()
      .then((result) => setSpike(JSON.stringify(result, null, 2)))
      .catch((err) => setSpike(`invokeRemote failed: ${err.message ?? JSON.stringify(err)}`))
      .finally(() => setSpiking(false));
  };

  if (tenant === null && !error) return <Spinner size="medium" />;

  return (
    <Stack space="space.200">
      <Heading size="medium">Connect your CI</Heading>
      {error && (
        <SectionMessage appearance="error" title="Something went wrong">
          <Text>{error}</Text>
        </SectionMessage>
      )}
      {tenant && (
        <Stack space="space.200">
          <Text>Installation ID: {tenant.installation_id}</Text>
          <Text>
            {tenant.has_ingest_key
              ? 'An ingest key exists for this installation. Generating a new one replaces it immediately.'
              : 'No ingest key yet. Generate one so your CI can upload test results.'}
          </Text>
          <Button appearance="primary" isDisabled={generating} onClick={generate}>
            {generating ? 'Generating…' : tenant.has_ingest_key ? 'Generate a new key' : 'Generate ingest key'}
          </Button>
        </Stack>
      )}
      <Stack space="space.100">
        <Heading size="small">SPIKE (issue #41): app system token probe</Heading>
        <Button isDisabled={spiking} onClick={runSpike}>
          {spiking ? 'Probing…' : 'Run system-token probe'}
        </Button>
        {spike && <CodeBlock language="json" text={spike} />}
      </Stack>
      {newKey && (
        <SectionMessage appearance="warning" title="Copy this key now - it won't be shown again">
          <Stack space="space.100">
            <Textfield isReadOnly value={newKey} aria-label="New ingest key" />
            <Text>Store it as a CI secret named INGEST_API_KEY. Then upload from CI with:</Text>
            <CodeBlock language="bash" text={uploadCommand()} />
          </Stack>
        </SectionMessage>
      )}
    </Stack>
  );
};
