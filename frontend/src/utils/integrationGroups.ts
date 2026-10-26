interface ConnectionLike {
  status: string;
  connected: boolean;
}

/**
 * Split the user's connections into what needs action (failed or awaiting a
 * request) and what is working. Healthy sources are not "attention" items.
 */
export function connectionGroups<T extends ConnectionLike>(connectors: T[]): { attention: T[]; connected: T[] } {
  const attention = connectors.filter((c) => c.status === "error" || c.status === "requested");
  const connected = connectors.filter((c) => c.connected && !attention.includes(c));
  return { attention, connected };
}
