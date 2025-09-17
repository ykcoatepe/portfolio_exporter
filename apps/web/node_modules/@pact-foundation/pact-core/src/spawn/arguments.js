"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Arguments = exports.PACT_NODE_NO_VALUE = exports.DEFAULT_ARG = void 0;
const _ = require("underscore");
const checkTypes = require("check-types");
exports.DEFAULT_ARG = 'DEFAULT';
exports.PACT_NODE_NO_VALUE = 'PACT_NODE_NO_VALUE';
const valFor = (v) => {
    if (typeof v === 'object') {
        return [JSON.stringify(v)];
    }
    return v !== exports.PACT_NODE_NO_VALUE ? [`${v}`] : [];
};
const mapFor = (mapping, v) => mapping === exports.DEFAULT_ARG ? valFor(v) : [mapping].concat(valFor(v));
const convertValue = (mapping, v) => {
    if (v && mapping) {
        return checkTypes.array(v)
            ? _.flatten(v.map((val) => mapFor(mapping, val)))
            : mapFor(mapping, v);
    }
    return [];
};
class Arguments {
    toArgumentsArray(args, mappings) {
        return _.chain(args instanceof Array ? args : [args])
            .map((x) => this.createArgumentsFromObject(x, mappings))
            .flatten()
            .value();
    }
    createArgumentsFromObject(args, mappings) {
        return _.chain(Object.keys(args))
            .reduce((acc, key) => mappings[key] === exports.DEFAULT_ARG
            ? convertValue(mappings[key], args[key]).concat(acc)
            : acc.concat(convertValue(mappings[key], args[key])), [])
            .value();
    }
}
exports.Arguments = Arguments;
exports.default = new Arguments();
//# sourceMappingURL=arguments.js.map