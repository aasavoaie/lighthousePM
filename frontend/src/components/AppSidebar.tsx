import {
  FOOTER_NAVIGATION,
  PRIMARY_NAVIGATION,
  type AppTab,
  type NavigationItem,
} from "../appNavigation";

type AppSidebarProps = {
  selectedTab: AppTab;
  isNavigationLocked: boolean;
  onSelectTab: (tab: AppTab) => void;
};

function NavigationItems({
  items,
  selectedTab,
  isNavigationLocked,
  onSelectTab,
}: AppSidebarProps & { items: ReadonlyArray<NavigationItem> }) {
  return items.map((item) => {
    if (item.kind === "link") {
      return (
        <button
          key={item.tab}
          type="button"
          className={`sidebar-link${item.subtle ? " subtle" : ""} ${selectedTab === item.tab ? "active" : ""}`}
          disabled={isNavigationLocked}
          onClick={() => onSelectTab(item.tab)}
        >
          <span className={`nav-icon ${item.iconClass}`} aria-hidden="true" />
          {item.label}
        </button>
      );
    }

    return (
      <div className="sidebar-menu-group" key={item.label}>
        <div className="sidebar-group-label">
          <span className={`nav-icon ${item.iconClass}`} aria-hidden="true" />
          {item.label}
        </div>
        <div className="sidebar-submenu">
          {item.items.map((subItem) => (
            <button
              key={subItem.tab}
              type="button"
              className={`sidebar-sublink ${selectedTab === subItem.tab ? "active" : ""}`}
              disabled={isNavigationLocked}
              onClick={() => onSelectTab(subItem.tab)}
            >
              {subItem.label}
            </button>
          ))}
        </div>
      </div>
    );
  });
}

export function AppSidebar({ selectedTab, isNavigationLocked, onSelectTab }: AppSidebarProps) {
  const navigationProps = { selectedTab, isNavigationLocked, onSelectTab };

  return (
    <aside className="sidebar-shell" aria-label="Primary">
      <div className="brand-mark">
        <span className="brand-icon" aria-hidden="true" />
        <strong>LighthousePM</strong>
      </div>
      <nav className="sidebar-nav" aria-label="Dashboard sections">
        <NavigationItems items={PRIMARY_NAVIGATION} {...navigationProps} />
      </nav>
      <div className="sidebar-footer">
        <NavigationItems items={FOOTER_NAVIGATION} {...navigationProps} />
      </div>
    </aside>
  );
}
