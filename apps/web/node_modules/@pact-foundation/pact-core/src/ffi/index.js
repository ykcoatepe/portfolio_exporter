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
Object.defineProperty(exports, "__esModule", { value: true });
exports.getFfiLib = exports.PACT_FFI_VERSION = void 0;
const bindings = require("bindings");
const logger_1 = __importStar(require("../logger"));
const ffiLib = bindings('pact.node');
exports.PACT_FFI_VERSION = '0.4.0';
let ffi;
let ffiLogLevel;
const initialiseFfi = (logLevel) => {
    logger_1.default.debug(`Initalising native core at log level '${logLevel}'`);
    ffiLogLevel = logLevel;
    ffiLib.pactffiInitWithLogLevel(logLevel);
    return ffiLib;
};
const getFfiLib = (logLevel = logger_1.DEFAULT_LOG_LEVEL) => {
    if (!ffi) {
        logger_1.default.trace('Initiliasing ffi for the first time');
        ffi = initialiseFfi(logLevel);
    }
    else {
        logger_1.default.trace('Ffi has already been initialised, no need to repeat it');
        if (logLevel !== ffiLogLevel) {
            logger_1.default.warn(`The pact native core has already been initialised at log level '${ffiLogLevel}'`);
            logger_1.default.warn(`The new requested log level '${logLevel}' will be ignored`);
        }
    }
    return ffi;
};
exports.getFfiLib = getFfiLib;
//# sourceMappingURL=index.js.map