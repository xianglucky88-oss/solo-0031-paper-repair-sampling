export function path(...parts) {
  return '/api/' + parts.map(encodeURIComponent).join('/');
}

export async function request(parts, body) {
  const response = await fetch(path(...parts), body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
