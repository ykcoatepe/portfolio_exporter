"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.standalone = void 0;
const path = __importStar(require("path"));
const install_1 = require("../standalone/install");
const pact_environment_1 = __importDefault(require("./pact-environment"));
const standalone = (platform = process.platform, arch = process.arch) => {
    const binName = (name) => `${name}${pact_environment_1.default.isWindows(platform) ? '.bat' : ''}`;
    const mock = binName('pact-mock-service');
    const message = binName('pact-message');
    const verify = binName('pact-provider-verifier');
    const broker = binName('pact-broker');
    const stub = binName('pact-stub-service');
    const pact = binName('pact');
    const pactflow = binName('pactflow');
    const basePath = path.join('standalone', (0, install_1.getBinaryEntry)(platform, arch).folderName, 'pact', 'bin');
    return {
        cwd: pact_environment_1.default.cwd,
        brokerPath: path.join(basePath, broker),
        brokerFullPath: path.resolve(pact_environment_1.default.cwd, basePath, broker).trim(),
        messagePath: path.join(basePath, message),
        messageFullPath: path
            .resolve(pact_environment_1.default.cwd, basePath, message)
            .trim(),
        mockServicePath: path.join(basePath, mock),
        mockServiceFullPath: path
            .resolve(pact_environment_1.default.cwd, basePath, mock)
            .trim(),
        stubPath: path.join(basePath, stub),
        stubFullPath: path.resolve(pact_environment_1.default.cwd, basePath, stub).trim(),
        pactPath: path.join(basePath, pact),
        pactFullPath: path.resolve(pact_environment_1.default.cwd, basePath, pact).trim(),
        pactflowPath: path.join(basePath, pactflow),
        pactflowFullPath: path
            .resolve(pact_environment_1.default.cwd, basePath, pactflow)
            .trim(),
        verifierPath: path.join(basePath, verify),
        verifierFullPath: path
            .resolve(pact_environment_1.default.cwd, basePath, verify)
            .trim(),
    };
};
exports.standalone = standalone;
exports.default = (0, exports.standalone)();
//# sourceMappingURL=pact-standalone.js.map