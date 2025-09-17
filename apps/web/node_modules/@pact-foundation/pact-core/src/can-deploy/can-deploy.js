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
exports.CanDeploy = void 0;
const promise_timeout_1 = require("promise-timeout");
const _ = __importStar(require("underscore"));
const checkTypes = require("check-types");
const logger_1 = __importStar(require("../logger"));
const pact_standalone_1 = __importDefault(require("../pact-standalone"));
const spawn_1 = __importStar(require("../spawn"));
const CannotDeployError_1 = require("./CannotDeployError");
class CanDeploy {
    constructor(passedOptions) {
        this.__argMapping = {
            name: '--pacticipant',
            version: '--version',
            latest: '--latest',
            to: '--to',
            pactBroker: '--broker-base-url',
            pactBrokerToken: '--broker-token',
            pactBrokerUsername: '--broker-username',
            pactBrokerPassword: '--broker-password',
            output: '--output',
            verbose: '--verbose',
            retryWhileUnknown: '--retry-while-unknown',
            retryInterval: '--retry-interval',
        };
        const options = { ...passedOptions };
        options.timeout = options.timeout || 60000;
        if (!options.output) {
            options.output = 'json';
        }
        checkTypes.assert.nonEmptyArray(options.pacticipants, 'Must provide at least one pacticipant');
        checkTypes.assert.nonEmptyString(options.pactBroker, 'Must provide the pactBroker argument');
        if (options.pactBrokerToken !== undefined) {
            checkTypes.assert.nonEmptyString(options.pactBrokerToken);
        }
        if (options.pactBrokerUsername !== undefined) {
            checkTypes.assert.string(options.pactBrokerUsername);
        }
        if (options.pactBrokerPassword !== undefined) {
            checkTypes.assert.string(options.pactBrokerPassword);
        }
        if (options.verbose === undefined && (0, logger_1.verboseIsImplied)()) {
            options.verbose = true;
        }
        if ((options.pactBrokerUsername && !options.pactBrokerPassword) ||
            (options.pactBrokerPassword && !options.pactBrokerUsername)) {
            throw new Error('Must provide both Pact Broker username and password. None needed if authentication on Broker is disabled.');
        }
        this.options = options;
    }
    static convertForSpawnBinary(options) {
        return _.flatten([_.omit(options, 'pacticipants')].concat(options.pacticipants.map(({ name, latest, version }) => [
            { name },
            version
                ? { version }
                : {
                    latest: latest === true ? spawn_1.PACT_NODE_NO_VALUE : latest,
                },
        ])));
    }
    canDeploy() {
        logger_1.default.info(`Asking broker at ${this.options.pactBroker} if it is possible to deploy`);
        const canDeployPromise = new Promise((resolve, reject) => {
            const instance = spawn_1.default.spawnBinary(pact_standalone_1.default.brokerFullPath, [
                { cliVerb: 'can-i-deploy' },
                ...CanDeploy.convertForSpawnBinary(this.options),
            ], this.__argMapping);
            const output = [];
            if (instance.stdout && instance.stderr) {
                instance.stdout.on('data', (l) => output.push(l));
                instance.stderr.on('data', (l) => output.push(l));
            }
            instance.once('close', (code) => {
                const result = output.join('\n');
                if (this.options.output === 'json') {
                    try {
                        const startIndex = output.findIndex((l) => l.toString().startsWith('{'));
                        if (startIndex === -1) {
                            logger_1.default.error(`can-i-deploy produced no json output:\n${result}`);
                            return reject(new Error(result));
                        }
                        if (startIndex !== 0) {
                            logger_1.default.warn(`can-i-deploy produced additional output: \n${output.slice(0, startIndex)}`);
                        }
                        const jsonPart = output.slice(startIndex).join('\n');
                        const parsed = JSON.parse(jsonPart);
                        if (code === 0 && parsed.summary.deployable) {
                            return resolve(parsed);
                        }
                        return reject(new CannotDeployError_1.CannotDeployError(parsed));
                    }
                    catch (e) {
                        logger_1.default.error(`can-i-deploy produced non-json output:\n${result}`);
                        return reject(new Error(result));
                    }
                }
                if (code === 0) {
                    logger_1.default.info(result);
                    return resolve(result);
                }
                logger_1.default.error(`can-i-deploy did not return success message:\n${result}`);
                return reject(new CannotDeployError_1.CannotDeployError(result));
            });
        });
        return (0, promise_timeout_1.timeout)(canDeployPromise, this.options.timeout).catch((err) => {
            if (err instanceof promise_timeout_1.TimeoutError) {
                throw new Error(`Timeout waiting for publication process to complete`);
            }
            throw err;
        });
    }
}
exports.CanDeploy = CanDeploy;
exports.default = (options) => new CanDeploy(options);
//# sourceMappingURL=can-deploy.js.map