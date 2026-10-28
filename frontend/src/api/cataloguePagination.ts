/** Fetch every bounded catalogue page; a failed page rejects the entire result. */
export async function cataloguePages<T>(fetchPage: (limit: number, offset: number) => Promise<T[]>): Promise<T[]> {
  const rows: T[] = [];
  const size = 200;
  for (let offset = 0; ; offset += size) {
    const page = await fetchPage(size, offset);
    rows.push(...page);
    if (page.length < size) return rows;
  }
}
