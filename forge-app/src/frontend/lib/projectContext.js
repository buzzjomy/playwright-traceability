// Pure helpers for reading the current Jira project from Forge's product
// context (useProductContext), kept out of the component so they're testable.

/**
 * The project key of the page the app is embedded in, or null when there
 * isn't one (context still loading, or a surface with no project).
 * On a jira:projectPage the context carries extension.project = {id, key, type}.
 */
export function projectKeyFromContext(context) {
  const key = context?.extension?.project?.key;
  return typeof key === 'string' && key.trim() ? key.trim() : null;
}

/** Which key to load: a manual override wins, then the detected project, then the fallback. */
export function resolveProjectKey({ override, detected, fallback }) {
  const typed = override?.trim();
  return typed || detected || fallback;
}
