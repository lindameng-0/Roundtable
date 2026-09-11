import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-alert-dialog";

const ConfirmationContext = createContext(null);
export const useConfirmation = () => useContext(ConfirmationContext);

export default function ConfirmationProvider({ children }) {
  const [request, setRequest] = useState(null);
  const resolver = useRef(null);
  const origin = useRef(null);
  const confirm = useCallback((options) => {
    if (resolver.current) return Promise.resolve(false);
    origin.current = document.activeElement;
    setRequest(options);
    return new Promise(resolve => { resolver.current = resolve; });
  }, []);
  const finish = (answer) => {
    const resolve = resolver.current;
    resolver.current = null;
    setRequest(null);
    resolve?.(answer);
  };
  return <ConfirmationContext.Provider value={confirm}>{children}
    <Dialog.Root open={!!request} onOpenChange={open => { if (!open) finish(false); }}>
      <Dialog.Portal><Dialog.Overlay className="confirmation-overlay" /><Dialog.Content className="confirmation-dialog" onCloseAutoFocus={event => { event.preventDefault(); if (origin.current?.isConnected) origin.current.focus(); }}>
        <Dialog.Title>{request?.title}</Dialog.Title>
        <Dialog.Description>{request?.description}</Dialog.Description>
        <div className="confirmation-actions"><Dialog.Cancel className="button button-quiet" onClick={() => finish(false)}>Cancel</Dialog.Cancel><Dialog.Action className={`button ${request?.destructive ? "button-danger" : "button-primary"}`} onClick={() => finish(true)}>{request?.action || "Continue"}</Dialog.Action></div>
      </Dialog.Content></Dialog.Portal>
    </Dialog.Root>
  </ConfirmationContext.Provider>;
}
