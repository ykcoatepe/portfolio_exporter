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
exports.Message = void 0;
const fs = require("fs");
const path = require("path");
const mkdirp = require("mkdirp");
const checkTypes = require("check-types");
const logger_1 = __importDefault(require("./logger"));
const spawn_1 = __importStar(require("./spawn"));
const pact_standalone_1 = __importDefault(require("./pact-standalone"));
class Message {
    constructor(passedOptions = {}) {
        this.__argMapping = {
            pactFileWriteMode: spawn_1.DEFAULT_ARG,
            dir: '--pact_dir',
            consumer: '--consumer',
            provider: '--provider',
            spec: '--pact_specification_version',
        };
        const options = { ...passedOptions };
        options.pactFileWriteMode = options.pactFileWriteMode || 'update';
        options.spec = options.spec || 3;
        checkTypes.assert.nonEmptyString(options.consumer || '', 'Must provide the consumer name');
        checkTypes.assert.nonEmptyString(options.provider || '', 'Must provide the provider name');
        checkTypes.assert.nonEmptyString(options.content || '', 'Must provide message content');
        checkTypes.assert.nonEmptyString(options.dir || '', 'Must provide pact output dir');
        if (options.spec) {
            checkTypes.assert.number(options.spec);
            checkTypes.assert.integer(options.spec);
            checkTypes.assert.positive(options.spec);
        }
        if (options.dir) {
            options.dir = path.resolve(options.dir);
            try {
                fs.statSync(options.dir).isDirectory();
            }
            catch (e) {
                mkdirp.sync(options.dir);
            }
        }
        if (options.content) {
            try {
                JSON.parse(options.content);
            }
            catch (e) {
                throw new Error('Unable to parse message content to JSON, invalid json supplied');
            }
        }
        if (options.consumer) {
            checkTypes.assert.string(options.consumer);
        }
        if (options.provider) {
            checkTypes.assert.string(options.provider);
        }
        this.options = options;
    }
    createMessage() {
        logger_1.default.info(`Creating message pact`);
        return new Promise((resolve, reject) => {
            const { pactFileWriteMode, content, ...restOptions } = this.options;
            const instance = spawn_1.default.spawnBinary(pact_standalone_1.default.messageFullPath, [{ pactFileWriteMode }, restOptions], this.__argMapping);
            const output = [];
            if (instance.stdout && instance.stderr && instance.stdin) {
                instance.stdout.on('data', (l) => output.push(l));
                instance.stderr.on('data', (l) => output.push(l));
                instance.stdin.write(content);
                instance.stdin.end();
            }
            instance.once('close', (code) => {
                const o = output.join('\n');
                logger_1.default.info(o);
                if (code === 0) {
                    return resolve(o);
                }
                return reject(o);
            });
        });
    }
}
exports.Message = Message;
exports.default = (options) => new Message(options);
//# sourceMappingURL=message.js.map