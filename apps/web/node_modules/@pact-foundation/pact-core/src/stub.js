"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.Stub = void 0;
const checkTypes = require("check-types");
const spawn_1 = require("./spawn");
const service_1 = require("./service");
const pact_standalone_1 = __importDefault(require("./pact-standalone"));
class Stub extends service_1.AbstractService {
    constructor(passedOptions = {}) {
        const options = { ...passedOptions };
        options.pactUrls = options.pactUrls || [];
        if (options.pactUrls) {
            checkTypes.assert.array.of.string(options.pactUrls);
        }
        checkTypes.assert.not.emptyArray(options.pactUrls);
        super(pact_standalone_1.default.stubFullPath, options, {
            pactUrls: spawn_1.DEFAULT_ARG,
            port: '--port',
            host: '--host',
            log: '--log',
            logLevel: '--log-level',
            ssl: '--ssl',
            sslcert: '--sslcert',
            sslkey: '--sslkey',
            cors: '--cors',
        });
        this.options = options;
    }
}
exports.Stub = Stub;
exports.default = (options) => new Stub(options);
//# sourceMappingURL=stub.js.map