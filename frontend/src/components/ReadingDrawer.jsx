import React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";

export default function ReadingDrawer({ drawer, close, origin, navigationTarget, children }) {
  return <Dialog.Root open={!!drawer} onOpenChange={open => { if (!open) close(); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="reading-drawer-scrim" />
      <Dialog.Content className={`reading-drawer reading-drawer-${drawer || "readers"}`} onCloseAutoFocus={event => {
        event.preventDefault();
        const target = navigationTarget.current ? document.getElementById(navigationTarget.current) : origin.current;
        target?.focus({ preventScroll: true });
        navigationTarget.current = null;
      }}>
        <div className="reading-drawer-heading">
          <div><Dialog.Title>{drawer === "contents" ? "Contents" : "Reader notebook"}</Dialog.Title><Dialog.Description>{drawer === "contents" ? "Find your place in the manuscript." : "Reflections, passage notes, and questions from your readers."}</Dialog.Description></div>
          <Dialog.Close className="drawer-close" aria-label="Close notebook or contents"><X size={18} /></Dialog.Close>
        </div>
        {children}
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
}
