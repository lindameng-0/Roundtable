import React from "react";

// Public support inbox confirmed by the owner.
export const SUPPORT_EMAIL = "roundtablesupport@gmail.com";

export default function PolicyContact() {
  return SUPPORT_EMAIL
    ? <a href={`mailto:${SUPPORT_EMAIL}`}>{SUPPORT_EMAIL}</a>
    : <span>Support email pending confirmation before publication.</span>;
}
