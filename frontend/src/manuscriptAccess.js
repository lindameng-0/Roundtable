const tokenKey = (manuscriptId) => `roundtable_manuscript_${manuscriptId}`;

export function rememberManuscriptAccess(manuscript) {
  if (!manuscript?.id || !manuscript?.access_token) return;
  localStorage.setItem(tokenKey(manuscript.id), manuscript.access_token);
}

export function forgetManuscriptAccess(manuscriptId) {
  if (manuscriptId) localStorage.removeItem(tokenKey(manuscriptId));
}

export function getManuscriptHeaders(manuscriptId) {
  const headers = {};
  const sessionToken = localStorage.getItem("session_token");
  const manuscriptToken = manuscriptId
    ? localStorage.getItem(tokenKey(manuscriptId))
    : null;
  if (sessionToken) headers.Authorization = `Bearer ${sessionToken}`;
  if (manuscriptToken) headers["X-Manuscript-Token"] = manuscriptToken;
  return headers;
}

export function manuscriptRequestConfig(manuscriptId, extra = {}) {
  return {
    ...extra,
    withCredentials: true,
    headers: {
      ...getManuscriptHeaders(manuscriptId),
      ...(extra.headers || {}),
    },
  };
}
