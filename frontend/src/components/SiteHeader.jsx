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
        {user ? <><NavLink to="/dashboard">Manuscripts</NavLink><NavLink to="/setup">New manuscript</NavLink></> : <><a href="/#how-it-works">How it works</a><NavLink to="/pricing">Plans &amp; credits</NavLink></>}
      </nav>
      <div className="site-account">{user ? <UserMenu /> : <Link to="/login" className="button button-quiet">Sign in</Link>}</div>
    </div>
  </header>;
}

export function SiteFooter() {
  return <footer className="site-footer no-print"><Brand /><p>A little perspective for your next draft.</p><Link to="/pricing">Plans &amp; credits</Link></footer>;
}
