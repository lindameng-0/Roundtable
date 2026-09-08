import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { getApi } from "../apiConfig";

export default function CreditBalance() {
  const [balance, setBalance] = useState(null);
  useEffect(() => {
    let active = true;
    const refresh = () => axios.get(`${getApi()}/billing/balance`, { withCredentials: true })
      .then(({ data }) => { if (active) setBalance(data.available_credits); })
      .catch(() => { if (active) setBalance(null); });
    refresh();
    window.addEventListener("focus", refresh);
    return () => { active = false; window.removeEventListener("focus", refresh); };
  }, []);
  return <Link to="/billing" className="text-xs text-ink-500 hover:text-ink-900 underline underline-offset-4">{balance === null ? "Credits & billing" : `${Number(balance).toLocaleString(undefined, { maximumFractionDigits: 2 })} credits`}</Link>;
}
