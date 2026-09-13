import { useEffect, useState } from "react";
import { listNotifications } from "../api/client";
import { href, useRoute } from "../router";

const POLL_MS = 60_000;
export const NOTIFICATIONS_CHANGED = "nexora:notifications-changed";

/** Pages that read, create or delete notifications/alerts call this so the
 * bell reflects the change at once instead of at the next poll. */
export function notifyNotificationsChanged(): void {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED));
}

/** Unread-count badge in the header. Polls the notifications endpoint (a
 * cheap DB read that also evaluates the user's alerts against cached data —
 * never a provider call) once a minute and on every route change. */
export function NotificationsBell() {
  const [unread, setUnread] = useState(0);
  const route = useRoute();

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      listNotifications({ unreadOnly: true, limit: 1 })
        .then((n) => !cancelled && setUnread(n.unread))
        .catch(() => {
          // the header must never break on a transient error
        });
    load();
    const timer = window.setInterval(load, POLL_MS);
    window.addEventListener(NOTIFICATIONS_CHANGED, load);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener(NOTIFICATIONS_CHANGED, load);
    };
  }, [route.path.join("/")]);

  return (
    <a href={href("alerts")} className="bell" aria-label={unread ? `${unread} notification(s) non lue(s)` : "Alertes et notifications"} title="Alertes et notifications">
      <span aria-hidden="true">🔔</span>
      {unread > 0 && <span className="bell-count">{unread > 99 ? "99+" : unread}</span>}
    </a>
  );
}
