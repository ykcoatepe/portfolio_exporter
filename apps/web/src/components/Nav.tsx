import { NavLink } from "react-router-dom";

export default function Nav(): JSX.Element {
  const link = "px-3 py-2 text-sm hover:underline";
  return (
    <nav aria-label="Primary" className="px-4 py-2">
      <NavLink to="/psd" className={link} end>
        Portfolio Sentinel Dashboard
      </NavLink>
    </nav>
  );
}
