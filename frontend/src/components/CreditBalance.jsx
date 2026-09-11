import React from "react";
import { Link } from "react-router-dom";

export default function CreditBalance() {
  return <Link to="/billing" className="text-xs text-ink-500 hover:text-ink-900 underline underline-offset-4">Your allowance</Link>;
}
