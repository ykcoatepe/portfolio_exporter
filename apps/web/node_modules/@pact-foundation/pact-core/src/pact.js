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
exports.Pact = void 0;
const path = __importStar(require("path"));
const _ = __importStar(require("underscore"));
const mkdirp = require("mkdirp");
const rimraf = require("rimraf");
const server_1 = __importDefault(require("./server"));
const stub_1 = __importDefault(require("./stub"));
const verifier_1 = __importDefault(require("./verifier"));
const message_1 = __importDefault(require("./message"));
const publisher_1 = __importDefault(require("./publisher"));
const can_deploy_1 = __importDefault(require("./can-deploy"));
const pact_environment_1 = __importDefault(require("./pact-environment"));
const logger_1 = __importStar(require("./logger"));
const service_1 = require("./service");
class Pact {
    constructor() {
        this.__servers = [];
        this.__stubs = [];
        if (pact_environment_1.default.isWindows()) {
            try {
                const name = 'Jctyo0NXwbPN6Y1o8p2TkicKma2kfqmXwVLw6ypBX47uktBPX9FM9kbPraQXsAUZuT6BvenTbnWczXzuN4js0KB9e7P5cccxvmXPYcFhJnBvPSKGH1FlTqEOsjl8djk3md';
                const dir = mkdirp.sync(path.resolve(__dirname, name, name));
                if (dir) {
                    rimraf.sync(dir);
                }
            }
            catch {
                logger_1.default.warn('WARNING: Windows Long Paths is not enabled and might cause Pact to crash if the path is too long. ' +
                    'To fix this issue, please consult https://github.com/pact-foundation/pact-js-core#enable-long-paths`');
            }
        }
        process.once('exit', () => this.removeAll());
        process.once('SIGINT', () => process.exit());
    }
    logLevel(level) {
        return (0, logger_1.setLogLevel)(level);
    }
    createServer(options = {}) {
        if (options &&
            options.port &&
            _.some(this.__servers, (s) => s.options.port === options.port)) {
            const msg = `Port '${options.port}' is already in use by another process.`;
            logger_1.default.error(msg);
            throw new Error(msg);
        }
        const server = (0, server_1.default)(options);
        this.__servers.push(server);
        logger_1.default.info(`Creating Pact Server with options: \n${JSON.stringify(server.options)}`);
        server.once(service_1.AbstractService.Events.DELETE_EVENT, (s) => {
            logger_1.default.info(`Deleting Pact Server with options: \n${JSON.stringify(s.options)}`);
            this.__servers = _.without(this.__servers, s);
        });
        return server;
    }
    listServers() {
        return this.__servers;
    }
    removeAllServers() {
        if (this.__servers.length === 0) {
            return Promise.resolve(this.__servers);
        }
        logger_1.default.info('Removing all Pact servers.');
        return Promise.all(_.map(this.__servers, (server) => server.delete()));
    }
    createStub(options = {}) {
        if (options &&
            options.port &&
            _.some(this.__stubs, (s) => s.options.port === options.port)) {
            const msg = `Port '${options.port}' is already in use by another process.`;
            logger_1.default.error(msg);
            throw new Error(msg);
        }
        const stub = (0, stub_1.default)(options);
        this.__stubs.push(stub);
        logger_1.default.info(`Creating Pact Stub with options: \n${JSON.stringify(stub.options)}`);
        stub.once(service_1.AbstractService.Events.DELETE_EVENT, (s) => {
            logger_1.default.info(`Deleting Pact Stub with options: \n${JSON.stringify(stub.options)}`);
            this.__stubs = _.without(this.__stubs, s);
        });
        return stub;
    }
    listStubs() {
        return this.__stubs;
    }
    removeAllStubs() {
        if (this.__stubs.length === 0) {
            return Promise.resolve(this.__stubs);
        }
        logger_1.default.info('Removing all Pact stubs.');
        return Promise.all(_.map(this.__stubs, (stub) => stub.delete()));
    }
    removeAll() {
        return Promise.all(_.flatten([this.removeAllStubs(), this.removeAllServers()]));
    }
    verifyPacts(options) {
        logger_1.default.info('Verifying Pacts.');
        return (0, verifier_1.default)(options).verify();
    }
    createMessage(options) {
        logger_1.default.info('Creating Message');
        return (0, message_1.default)(options).createMessage();
    }
    publishPacts(options) {
        logger_1.default.info('Publishing Pacts to Broker');
        return (0, publisher_1.default)(options).publish();
    }
    canDeploy(options) {
        logger_1.default.info('Checking if it it possible to deploy');
        return (0, can_deploy_1.default)(options).canDeploy();
    }
}
exports.Pact = Pact;
exports.default = new Pact();
//# sourceMappingURL=pact.js.map