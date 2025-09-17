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
exports.Publisher = void 0;
const path = require("path");
const fs = require("fs");
const promise_timeout_1 = require("promise-timeout");
const checkTypes = require("check-types");
const logger_1 = __importStar(require("./logger"));
const spawn_1 = __importStar(require("./spawn"));
const pact_standalone_1 = __importDefault(require("./pact-standalone"));
class Publisher {
    constructor(passedOptions) {
        this.__argMapping = {
            pactFilesOrDirs: spawn_1.DEFAULT_ARG,
            pactBroker: '--broker-base-url',
            pactBrokerUsername: '--broker-username',
            pactBrokerPassword: '--broker-password',
            pactBrokerToken: '--broker-token',
            tags: '--tag',
            consumerVersion: '--consumer-app-version',
            verbose: '--verbose',
            buildUrl: '--build-url',
            branch: '--branch',
            autoDetectVersionProperties: '--auto-detect-version-properties',
        };
        this.options = passedOptions || {};
        this.options.tags = this.options.tags || [];
        this.options.timeout = this.options.timeout || 60000;
        checkTypes.assert.nonEmptyString(this.options.pactBroker, 'Must provide the pactBroker argument');
        checkTypes.assert.nonEmptyString(this.options.consumerVersion, 'Must provide the consumerVersion argument');
        checkTypes.assert.arrayLike(this.options.pactFilesOrDirs, 'Must provide the pactFilesOrDirs argument');
        checkTypes.assert.nonEmptyArray(this.options.pactFilesOrDirs, 'Must provide the pactFilesOrDirs argument with an array');
        if (this.options.pactFilesOrDirs) {
            checkTypes.assert.array.of.string(this.options.pactFilesOrDirs);
            this.options.pactFilesOrDirs = this.options.pactFilesOrDirs.map((v) => {
                const newPath = path.resolve(v);
                if (!fs.existsSync(newPath)) {
                    throw new Error(`Path '${v}' given in pactFilesOrDirs does not exists.`);
                }
                return newPath;
            });
        }
        if (this.options.pactBroker) {
            checkTypes.assert.string(this.options.pactBroker);
        }
        if (this.options.pactBrokerUsername) {
            checkTypes.assert.string(this.options.pactBrokerUsername);
        }
        if (this.options.pactBrokerPassword) {
            checkTypes.assert.string(this.options.pactBrokerPassword);
        }
        if (this.options.verbose === undefined && (0, logger_1.verboseIsImplied)()) {
            this.options.verbose = true;
        }
        if ((this.options.pactBrokerUsername && !this.options.pactBrokerPassword) ||
            (this.options.pactBrokerPassword && !this.options.pactBrokerUsername)) {
            throw new Error('Must provide both Pact Broker username and password. None needed if authentication on Broker is disabled.');
        }
        if (this.options.pactBrokerToken &&
            (this.options.pactBrokerUsername || this.options.pactBrokerPassword)) {
            throw new Error('Must provide pactBrokerToken or pactBrokerUsername/pactBrokerPassword but not both.');
        }
        if (this.options.branch) {
            checkTypes.assert.string(this.options.branch);
        }
        if (this.options.autoDetectVersionProperties) {
            checkTypes.assert.boolean(this.options.autoDetectVersionProperties);
        }
    }
    publish() {
        logger_1.default.info(`Publishing pacts to broker at: ${this.options.pactBroker}`);
        return (0, promise_timeout_1.timeout)(new Promise((resolve, reject) => {
            const instance = spawn_1.default.spawnBinary(pact_standalone_1.default.brokerFullPath, [{ cliVerb: 'publish' }, this.options], this.__argMapping);
            const output = [];
            if (instance.stderr && instance.stdout) {
                instance.stdout.on('data', (l) => output.push(l));
                instance.stderr.on('data', (l) => output.push(l));
            }
            instance.once('close', (code) => {
                const o = output.join('\n');
                const pactUrls = /https?:\/\/.*\/pacts\/.*$/gim.exec(o);
                if (code !== 0) {
                    const message = `Pact publication failed with non-zero exit code. Full output was:\n${o}`;
                    logger_1.default.error(message);
                    return reject(new Error(message));
                }
                if (!pactUrls) {
                    const message = `Publication appeared to fail, as we did not detect any pact URLs in the following output:\n${o}`;
                    logger_1.default.error(message);
                    return reject(new Error(message));
                }
                logger_1.default.info(o);
                return resolve(pactUrls);
            });
        }), this.options.timeout).catch((err) => {
            if (err instanceof promise_timeout_1.TimeoutError) {
                throw new Error(`Timeout waiting for publication process to complete`);
            }
            throw err;
        });
    }
}
exports.Publisher = Publisher;
exports.default = (options) => new Publisher(options);
//# sourceMappingURL=publisher.js.map