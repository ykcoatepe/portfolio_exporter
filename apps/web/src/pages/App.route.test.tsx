import { screen } from "@testing-library/react";

import App from "../App";
import { renderWithClient } from "../test/queryClient";

test("default route renders the PSD dashboard", async () => {
  renderWithClient(<App />);

  expect(await screen.findByRole("heading", { name: /Single Stocks/i })).toBeInTheDocument();
});
