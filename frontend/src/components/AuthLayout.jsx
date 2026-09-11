import React from "react";
import { TableMark } from "./Brand";
import SiteHeader, { SiteFooter } from "./SiteHeader";

export default function AuthLayout({ children }) {
  return <div className="auth-page"><SiteHeader /><main id="main-content" className="auth-layout" tabIndex={-1}>
    <aside className="auth-story"><TableMark className="auth-table-mark" /><p className="small-note">A place for your work in progress</p><h2>Every story deserves<br />a thoughtful reader.</h2><p>Meet a panel of AI readers who notice different things. Find the moments that draw them in, and the places they lose the thread.</p><div className="auth-signature">Your words. A fresh perspective.</div></aside>
    <section className="auth-form-panel">{children}</section>
  </main><SiteFooter /></div>;
}
