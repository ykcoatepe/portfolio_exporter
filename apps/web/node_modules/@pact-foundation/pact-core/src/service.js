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
exports.AbstractService = void 0;
const path = require("path");
const fs = require("fs");
const events = require("events");
const promise_timeout_1 = require("promise-timeout");
const mkdirp = require("mkdirp");
const checkTypes = require("check-types");
const needle = require("needle");
const spawn_1 = __importDefault(require("./spawn"));
const logger_1 = __importStar(require("./logger"));
const { setTimeout } = global;
const RETRY_AMOUNT = 60;
const getTimeout = (options) => options.timeout || 30000;
const getRetryTickTime = (options) => Math.round(getTimeout(options) / RETRY_AMOUNT);
class AbstractService extends events.EventEmitter {
    constructor(command, options, argMapping, cliVerb) {
        super();
        if (options.logLevel) {
            (0, logger_1.setLogLevel)(options.logLevel);
            if (options.logLevel === 'fatal') {
                options.logLevel = 'error';
            }
            else if (options.logLevel === 'trace') {
                options.logLevel = 'debug';
            }
            options.logLevel = options.logLevel.toUpperCase();
        }
        options.ssl = options.ssl || false;
        options.cors = options.cors || false;
        options.host = options.host || 'localhost';
        if (options.port) {
            checkTypes.assert.number(options.port);
            checkTypes.assert.integer(options.port);
            checkTypes.assert.positive(options.port);
            if (!checkTypes.inRange(options.port, 0, 65535)) {
                throw new Error(`Port number ${options.port} is not in the range 0-65535`);
            }
            if (checkTypes.not.inRange(options.port, 1024, 49151)) {
                logger_1.default.warn('Like a Boss, you used a port outside of the recommended range (1024 to 49151); I too like to live dangerously.');
            }
        }
        checkTypes.assert.boolean(options.ssl);
        if ((options.sslcert && !options.sslkey) ||
            (!options.sslcert && options.sslkey)) {
            throw new Error('Custom ssl certificate and key must be specified together.');
        }
        if (options.sslcert) {
            try {
                fs.statSync(path.normalize(options.sslcert)).isFile();
            }
            catch (e) {
                throw new Error(`Custom ssl certificate not found at path: ${options.sslcert}`);
            }
        }
        if (options.sslkey) {
            try {
                fs.statSync(path.normalize(options.sslkey)).isFile();
            }
            catch (e) {
                throw new Error(`Custom ssl key not found at path: ${options.sslkey}`);
            }
        }
        if (options.sslcert && options.sslkey) {
            options.ssl = true;
        }
        checkTypes.assert.boolean(options.cors);
        if (options.log) {
            const fileObj = path.parse(path.normalize(options.log));
            try {
                fs.statSync(fileObj.dir).isDirectory();
            }
            catch (e) {
                mkdirp.sync(fileObj.dir);
            }
        }
        if (options.host) {
            checkTypes.assert.string(options.host);
        }
        this.options = options;
        this.__running = false;
        this.__cliVerb = cliVerb;
        this.__serviceCommand = command;
        this.__argMapping = argMapping;
    }
    static get Events() {
        return {
            START_EVENT: 'start',
            STOP_EVENT: 'stop',
            DELETE_EVENT: 'delete',
        };
    }
    start() {
        if (this.__instance && this.__instance.connected) {
            logger_1.default.warn(`You already have a process running with PID: ${this.__instance.pid}`);
            return Promise.resolve(this);
        }
        this.__instance = this.spawnBinary();
        this.__instance.once('close', () => this.stop());
        if (!this.options.port) {
            const catchPort = (data) => {
                const match = data.match(/port=([0-9]+)/);
                if (match && match[1]) {
                    this.options.port = parseInt(match[1], 10);
                    if (this?.__instance?.stdout) {
                        this.__instance.stdout.removeListener('data', catchPort);
                    }
                    logger_1.default.info(`Pact running on port ${this.options.port}`);
                }
            };
            if (this?.__instance?.stdout) {
                this.__instance.stdout.on('data', catchPort);
            }
        }
        if (this?.__instance?.stderr) {
            this.__instance.stderr.on('data', (data) => logger_1.default.error(`Pact Binary Error: ${data}`));
        }
        return (0, promise_timeout_1.timeout)(this.__waitForServiceUp(), getTimeout(this.options))
            .then(() => {
            this.__running = true;
            this.emit(AbstractService.Events.START_EVENT, this);
            return this;
        })
            .catch((err) => {
            if (err instanceof promise_timeout_1.TimeoutError) {
                throw new Error(`Timeout while waiting to start Pact with PID: ${this.__instance ? this.__instance.pid : 'No Instance'}`);
            }
            throw err;
        });
    }
    stop() {
        const pid = this.__instance ? this.__instance.pid : -1;
        return (0, promise_timeout_1.timeout)(Promise.resolve(this.__instance)
            .then(spawn_1.default.killBinary)
            .then(() => this.__waitForServiceDown()), getTimeout(this.options))
            .catch((err) => {
            if (err instanceof promise_timeout_1.TimeoutError) {
                throw new Error(`Timeout while waiting to stop Pact with PID '${pid}'`);
            }
            throw err;
        })
            .then(() => {
            this.__running = false;
            this.emit(AbstractService.Events.STOP_EVENT, this);
            return this;
        });
    }
    delete() {
        return this.stop().then(() => {
            this.emit(AbstractService.Events.DELETE_EVENT, this);
            return this;
        });
    }
    spawnBinary() {
        return spawn_1.default.spawnBinary(this.__serviceCommand, this.__cliVerb ? [this.__cliVerb, this.options] : [this.options], this.__argMapping);
    }
    __waitForServiceUp() {
        let amount = 0;
        const waitPromise = new Promise((resolve, reject) => {
            const retry = () => {
                if (amount >= RETRY_AMOUNT) {
                    reject(new Error(`Pact startup failed; tried calling service ${RETRY_AMOUNT} times with no result.`));
                }
                setTimeout(check.bind(this), getRetryTickTime(this.options));
            };
            const check = () => {
                amount += 1;
                if (this.options.port) {
                    this.__call(this.options).then(() => resolve(), retry.bind(this));
                }
                else {
                    retry();
                }
            };
            check();
        });
        return waitPromise;
    }
    __waitForServiceDown() {
        let amount = 0;
        const checkPromise = new Promise((resolve, reject) => {
            const check = () => {
                amount += 1;
                if (this.options.port) {
                    this.__call(this.options).then(() => {
                        if (amount >= RETRY_AMOUNT) {
                            reject(new Error(`Pact stop failed; tried calling service ${RETRY_AMOUNT} times with no result.`));
                            return;
                        }
                        setTimeout(check, getRetryTickTime(this.options));
                    }, () => resolve());
                }
                else {
                    resolve();
                }
            };
            check();
        });
        return checkPromise;
    }
    __call(options) {
        const config = {
            method: 'GET',
            headers: {
                'X-Pact-Mock-Service': 'true',
                'Content-Type': 'application/json',
            },
        };
        if (options.ssl) {
            process.env['NODE_TLS_REJECT_UNAUTHORIZED'] = '0';
            config.rejectUnauthorized = false;
            config.agent = false;
        }
        return needle('get', `http${options.ssl ? 's' : ''}://${options.host}:${options.port}`, config).then((res) => {
            if (res.statusCode !== 200) {
                throw new Error(`HTTP Error: '${JSON.stringify(res)}'`);
            }
        });
    }
}
exports.AbstractService = AbstractService;
//# sourceMappingURL=service.js.map