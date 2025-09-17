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
exports.Spawn = void 0;
const spawn = require("cross-spawn");
const cp = require("child_process");
const path = __importStar(require("path"));
const logger_1 = __importDefault(require("../logger"));
const pact_environment_1 = __importDefault(require("../pact-environment"));
const arguments_1 = __importStar(require("./arguments"));
class Spawn {
    get cwd() {
        return path.resolve(__dirname, '..');
    }
    spawnBinary(command, args = {}, argMapping = {}) {
        const envVars = JSON.parse(JSON.stringify(process.env));
        envVars.PACT_EXECUTING_LANGUAGE = 'node.js';
        envVars.PACT_EXECUTING_LANGUAGE_VERSION = process.versions.node;
        delete envVars.RUBYGEMS_GEMDEPS;
        const opts = {
            cwd: pact_environment_1.default.cwd,
            detached: !pact_environment_1.default.isWindows(),
            env: envVars,
        };
        const spawnArgs = arguments_1.default.toArgumentsArray(args, {
            cliVerb: arguments_1.DEFAULT_ARG,
            ...argMapping,
        });
        logger_1.default.debug(`Starting pact binary '${command}', with arguments [${spawnArgs.join(' ')}]`);
        logger_1.default.trace(`Environment: ${JSON.stringify(opts)}`);
        const instance = spawn(command, spawnArgs, opts);
        if (instance.stderr && instance.stdout) {
            instance.stdout.on('data', logger_1.default.debug.bind(logger_1.default));
            instance.stdout.setEncoding('utf8');
            instance.stderr.setEncoding('utf8');
            instance.stderr.on('data', logger_1.default.debug.bind(logger_1.default));
        }
        instance.on('error', logger_1.default.error.bind(logger_1.default));
        instance.once('close', (code) => {
            if (code !== 0) {
                logger_1.default.warn(`Pact exited with code ${code}.`);
            }
        });
        logger_1.default.debug(`Created '${command}' process with PID: ${instance.pid}`);
        return instance;
    }
    killBinary(binary) {
        if (binary) {
            const { pid } = binary;
            logger_1.default.info(`Removing Pact process with PID: ${pid}`);
            binary.removeAllListeners();
            try {
                if (pid) {
                    if (pact_environment_1.default.isWindows()) {
                        cp.execSync(`taskkill /f /t /pid ${pid}`);
                    }
                    else {
                        process.kill(-pid, 'SIGINT');
                    }
                }
            }
            catch (e) {
                return false;
            }
        }
        return true;
    }
}
exports.Spawn = Spawn;
exports.default = new Spawn();
//# sourceMappingURL=spawn.js.map