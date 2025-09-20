import { MemoryRouter } from "react-router-dom";
import { screen } from "@testing-library/react";

import { renderWithClient } from "../test/queryClient";
import Nav from "./Nav";

test("links dashboard navigation to /psd", () => {
  renderWithClient(
    <MemoryRouter initialEntries={["/psd"]}>
      <Nav />
    </MemoryRouter>,
  );

  const link = screen.getByRole("link", { name: /Portfolio Sentinel Dashboard/i });
  expect(link).toHaveAttribute("href", "/psd");
});
