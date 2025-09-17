import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "../mocks/server";

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
