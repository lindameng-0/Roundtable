export function getManuscriptHeaders() {
  return {};
}

export function manuscriptRequestConfig(_manuscriptId, extra = {}) {
  return {
    ...extra,
    withCredentials: true,
    headers: {
      ...getManuscriptHeaders(manuscriptId),
      ...(extra.headers || {}),
    },
  };
}
