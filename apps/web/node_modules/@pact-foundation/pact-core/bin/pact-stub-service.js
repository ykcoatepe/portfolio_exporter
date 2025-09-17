#!/usr/bin/env node
"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const childProcess = require("child_process");
const pact_standalone_1 = __importDefault(require("../src/pact-standalone"));
const { status } = childProcess.spawnSync(pact_standalone_1.default.stubFullPath, process.argv.slice(2), {
    stdio: 'inherit',
});
process.exit(status);
//# sourceMappingURL=pact-stub-service.js.map