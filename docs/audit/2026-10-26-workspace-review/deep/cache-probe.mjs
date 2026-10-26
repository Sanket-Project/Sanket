// Isolated library probe; no browser, network, credentials or application state.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
const require = createRequire(resolve(dirname(fileURLToPath(import.meta.url)), '../../../../frontend/package.json'));
const { QueryClient } = require('@tanstack/react-query');
const client = new QueryClient({ defaultOptions: { queries: { staleTime: 30000 } } });
const queryKey = ['decisions', 'fashion', 'open'];
client.setQueryData(queryKey, { tenant: 'A', decisions: ['A-private-row'] });
let calls = 0;
const result = await client.fetchQuery({ queryKey, queryFn: async () => {
  calls++;
  return { tenant: 'B', decisions: [] };
}});
console.log(JSON.stringify({ result, tenantBNetworkCalls: calls }, null, 2));
client.clear();
