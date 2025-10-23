import {
  Children,
  type MouseEventHandler,
  type ReactElement,
  type ReactNode,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

type NavigateOptions = {
  replace?: boolean;
};

type RouterContextValue = {
  location: string;
  navigate: (to: string, options?: NavigateOptions) => void;
};

const RouterContext = createContext<RouterContextValue | null>(null);

function normalizePath(value: string | undefined | null): string {
  if (!value) {
    return "/";
  }
  let normalized = value.startsWith("/") ? value : `/${value}`;
  if (normalized.length > 1) {
    normalized = normalized.replace(/\/+$/u, "");
    if (!normalized) {
      normalized = "/";
    }
  }
  return normalized;
}

function useRouter(): RouterContextValue {
  const ctx = useContext(RouterContext);
  if (!ctx) {
    throw new Error("Router components must be rendered within a router provider.");
  }
  return ctx;
}

export interface RouteProps {
  path?: string;
  element: ReactNode;
}

export function Route(_: RouteProps): null {
  return null;
}

function matchPath(path: string | undefined, location: string): boolean {
  if (!path || path === "") {
    return location === "/";
  }
  if (path === "*") {
    return true;
  }
  const target = normalizePath(path);
  if (target === location) {
    return true;
  }
  if (target.endsWith("/*")) {
    const prefix = target.slice(0, -2) || "/";
    return location === prefix || location.startsWith(`${prefix}/`);
  }
  return false;
}

export function Routes({ children }: { children?: ReactNode }): JSX.Element | null {
  const { location } = useRouter();
  const routeElements = Children.toArray(children) as ReactElement<RouteProps>[];
  for (const child of routeElements) {
    if (!isValidElement<RouteProps>(child)) {
      continue;
    }
    const { path, element } = child.props;
    if (matchPath(path, location)) {
      return <>{element}</>;
    }
  }
  return null;
}

export function Navigate({ to, replace }: { to: string; replace?: boolean }): null {
  const { navigate } = useRouter();
  useEffect(() => {
    navigate(to, { replace });
  }, [navigate, replace, to]);
  return null;
}

export function BrowserRouter({ children }: { children?: ReactNode }): JSX.Element {
  const [location, setLocation] = useState(() => normalizePath(window.location?.pathname));

  const navigate = useCallback(
    (to: string, options?: NavigateOptions) => {
      const target = normalizePath(to);
      if (options?.replace) {
        window.history.replaceState(null, "", target);
      } else {
        window.history.pushState(null, "", target);
      }
      setLocation(target);
    },
    [],
  );

  useEffect(() => {
    const handlePop = () => {
      setLocation(normalizePath(window.location?.pathname));
    };
    window.addEventListener("popstate", handlePop);
    return () => window.removeEventListener("popstate", handlePop);
  }, []);

  const value = useMemo<RouterContextValue>(() => ({ location, navigate }), [location, navigate]);

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function MemoryRouter({
  children,
  initialEntries,
}: {
  children?: ReactNode;
  initialEntries?: string[];
}): JSX.Element {
  const entries = initialEntries && initialEntries.length > 0 ? initialEntries : ["/"];
  const [location, setLocation] = useState(() => normalizePath(entries[0]));

  const navigate = useCallback((to: string) => {
    setLocation(normalizePath(to));
  }, []);

  const value = useMemo<RouterContextValue>(() => ({ location, navigate }), [location, navigate]);

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

type NavLinkClass = string | ((state: { isActive: boolean }) => string);

type NavLinkChildren = ReactNode | ((state: { isActive: boolean }) => ReactNode);

export interface NavLinkProps extends Omit<
  React.AnchorHTMLAttributes<HTMLAnchorElement>,
  "href" | "className" | "children"
> {
  to: string;
  className?: NavLinkClass;
  end?: boolean;
  children?: NavLinkChildren;
}

export function NavLink({
  to,
  className,
  end,
  children,
  onClick,
  ...anchorProps
}: NavLinkProps): JSX.Element {
  const { location, navigate } = useRouter();
  const target = normalizePath(to);
  const isExact = location === target;
  const isActive = end ? isExact : isExact || location.startsWith(`${target}/`);

  const resolvedClassName = typeof className === "function" ? className({ isActive }) : className;
  const content = typeof children === "function" ? children({ isActive }) : children;

  const handleClick: MouseEventHandler<HTMLAnchorElement> = (event) => {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.altKey ||
      event.ctrlKey ||
      event.shiftKey
    ) {
      return;
    }
    event.preventDefault();
    navigate(target);
  };

  return (
    <a
      {...anchorProps}
      href={target}
      className={resolvedClassName}
      aria-current={isActive ? "page" : undefined}
      onClick={handleClick}
    >
      {content}
    </a>
  );
}

export function useLocation(): string {
  return useRouter().location;
}

export function useNavigate(): (to: string, options?: NavigateOptions) => void {
  const { navigate } = useRouter();
  return navigate;
}
