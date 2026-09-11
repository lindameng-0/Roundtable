import React from "react";
import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { UserMenu } from "./UserMenu";
import Brand from "./Brand";

export default function SiteHeader() {
  const { user } = useAuth();
  return <header className="site-header no-print">
    <div className="site-header-inner">
      <Brand to={user ? "/dashboard" : "/"} />
      <nav className="site-nav" aria-label="Main navigation">
        {user ? <><NavLink to="/dashboard">Manuscripts</NavLink><NavLink to="/setup">New manuscript</NavLink>{user.is_owner && <NavLink to="/owner/analytics">Analytics</NavLink>}</> : <><a href="/#how-it-works">How it works</a><NavLink to="/use-cases">Use cases</NavLink><NavLink to="/pricing">Plans &amp; credits</NavLink></>}
      </nav>
      <div className="site-account">{user ? <UserMenu /> : <Link to="/login" className="button button-quiet">Sign in</Link>}</div>
    </div>
  </header>;
}

export function SiteFooter() {
  return <footer className="site-footer no-print"><Brand /><p>A little perspective for your next draft.</p><nav className="site-footer-links" aria-label="Resources, pricing and policies"><Link to="/use-cases">Writing use cases</Link><Link to="/connect-assistant">Assistant connections</Link><Link to="/sample-reading">Sample reading</Link><Link to="/beta-readers">Beta readers</Link><Link to="/ai-beta-reader">AI beta readers</Link><Link to="/manuscript-feedback">Manuscript feedback</Link><Link to="/pricing">Pricing</Link><Link to="/terms">Terms of service</Link><Link to="/privacy">Privacy policy</Link><Link to="/refunds">Refund policy</Link></nav></footer>;
}
