"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.Server = void 0;
const path = require("path");
const fs = require("fs");
const mkdirp = require("mkdirp");
const checkTypes = require("check-types");
const pact_standalone_1 = __importDefault(require("./pact-standalone"));
const service_1 = require("./service");
class Server extends service_1.AbstractService {
    constructor(passedOptions = {}) {
        const options = { ...passedOptions };
        options.dir = options.dir ? path.resolve(options.dir) : process.cwd();
        options.pactFileWriteMode = options.pactFileWriteMode || 'overwrite';
        if (options.spec) {
            checkTypes.assert.number(options.spec);
            checkTypes.assert.integer(options.spec);
            checkTypes.assert.positive(options.spec);
        }
        if (options.dir) {
            const dir = path.resolve(options.dir);
            try {
                fs.statSync(dir).isDirectory();
            }
            catch (e) {
                mkdirp.sync(dir);
            }
        }
        if (options.log) {
            options.log = path.resolve(options.log);
        }
        if (options.sslcert) {
            options.sslcert = path.resolve(options.sslcert);
        }
        if (options.sslkey) {
            options.sslkey = path.resolve(options.sslkey);
        }
        if (options.consumer) {
            checkTypes.assert.string(options.consumer);
        }
        if (options.provider) {
            checkTypes.assert.string(options.provider);
        }
        if (options.logLevel) {
            options.logLevel = options.logLevel.toLowerCase();
        }
        if (options.monkeypatch) {
            checkTypes.assert.string(options.monkeypatch);
            try {
                fs.statSync(path.normalize(options.monkeypatch)).isFile();
            }
            catch (e) {
                throw new Error(`Monkeypatch ruby file not found at path: ${options.monkeypatch}`);
            }
        }
        super(pact_standalone_1.default.mockServiceFullPath, options, {
            port: '--port',
            host: '--host',
            log: '--log',
            ssl: '--ssl',
            sslcert: '--sslcert',
            sslkey: '--sslkey',
            cors: '--cors',
            dir: '--pact_dir',
            spec: '--pact_specification_version',
            pactFileWriteMode: '--pact-file-write-mode',
            consumer: '--consumer',
            provider: '--provider',
            monkeypatch: '--monkeypatch',
            logLevel: '--log-level',
        }, { cliVerb: 'service' });
        this.options = options;
    }
}
exports.Server = Server;
exports.default = (options) => new Server(options);
//# sourceMappingURL=server.js.map