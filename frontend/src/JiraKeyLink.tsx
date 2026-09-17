// Shared between InventoryView and CoverageView - links a Jira key to the
// real ticket when a connection is configured, otherwise plain text.
export function JiraKeyLink({ jiraKey, siteUrl }: { jiraKey: string; siteUrl: string | null }) {
  if (!siteUrl) return <span className="jira-key">{jiraKey}</span>;
  return (
    <a className="jira-key" href={`${siteUrl.replace(/\/$/, '')}/browse/${jiraKey}`} target="_blank" rel="noreferrer">
      {jiraKey}
    </a>
  );
}
