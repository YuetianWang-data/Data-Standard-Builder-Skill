# Centralizes input aliases, supported file types, and output label constants.

FIELD_ALIASES = {
    "table_name": [
        "表名",
        "数据表名",
        "资源表名",
        "表英文名",
        "table",
        "table_name",
        "tablename",
    ],
    "table_comment": [
        "表中文名",
        "数据表中文名",
        "表说明",
        "表描述",
        "table_comment",
        "table_description",
    ],
    "field_name": [
        "字段名",
        "字段英文名",
        "列名",
        "属性名",
        "column",
        "column_name",
        "field",
        "field_name",
        "fieldname",
    ],
    "field_comment": [
        "字段中文名",
        "字段名称",
        "列中文名",
        "属性中文名",
        "中文名称",
        "字段说明",
        "字段描述",
        "column_comment",
        "field_comment",
        "description",
    ],
    "data_type": ["数据类型", "字段类型", "类型", "data_type", "datatype", "column_type"],
    "length": ["长度", "字段长度", "数据长度", "精度", "length", "precision"],
    "nullable": ["是否为空", "允许为空", "可空", "nullable", "is_nullable"],
    "primary_key": ["主键", "是否主键", "primary_key", "is_primary_key", "pk"],
    "default": ["默认值", "缺省值", "default", "column_default"],
}

STANDARD_ALIASES = {
    "chinese_name": [
        "数据元中文名称",
        "数据元名称",
        "中文名称",
        "中文名",
        "名称",
        "字段中文名",
    ],
    "english_name": [
        "数据元英文名称",
        "英文名称",
        "英文名",
        "字段英文名",
        "字段名",
    ],
    "standard_code": [
        "数据元标识符",
        "数据元内部标识符",
        "数据元编号",
        "数据元代码",
        "内部标识符",
        "内部标识",
        "标识符",
        "编号",
        "代码",
    ],
    "definition": ["定义", "数据元定义", "说明", "描述", "业务含义"],
    "data_type": ["数据类型", "类型", "数据元类型"],
    "data_format": ["数据格式", "表示格式", "格式", "长度"],
    "value_domain": ["值域", "允许值", "取值范围", "代码集", "约束"],
    "unit": ["计量单位", "单位"],
    "synonyms": ["同义名称", "同义词", "别名"],
    "remarks": ["备注", "附注"],
}

RULE_ALIASES = {
    "rule_id": ["规则编号", "规则id", "编号", "rule_id", "id"],
    "system_name": ["系统名称", "所属系统", "system_name", "system"],
    "table_name": ["表名称", "表名", "数据表名", "table_name", "table"],
    "model_name": ["模型名称", "评测模型", "model_name", "model"],
    "rule_name": ["规则名称", "规则名", "名称", "rule_name", "name"],
    "rule_content": [
        "规则描述",
        "规则内容",
        "业务规则",
        "标准内容",
        "约束",
        "说明",
        "rule_content",
        "content",
    ],
    "problem_description": [
        "问题描述",
        "异常描述",
        "problem_description",
        "issue_description",
    ],
    "rule_status": ["规则状态", "状态", "rule_status", "status"],
    "scope": ["适用范围", "范围", "scope"],
    "target": ["适用对象", "目标字段", "目标", "target"],
    "severity": ["严重程度", "级别", "强制性", "severity"],
    "source": ["来源", "source"],
}

SUPPORTED_SCHEMA_SUFFIXES = {".sql", ".db", ".sqlite", ".sqlite3", ".csv", ".xlsx", ".xlsm", ".json"}
SUPPORTED_STANDARD_SUFFIXES = {".pdf", ".csv", ".xlsx", ".xlsm", ".json"}
SUPPORTED_RULE_SUFFIXES = {".txt", ".md", ".csv", ".xlsx", ".xlsm", ".json"}

CONSTRAINT_WORDS = (
    "NOT NULL",
    "NULL",
    "DEFAULT",
    "PRIMARY KEY",
    "UNIQUE",
    "REFERENCES",
    "CHECK",
    "COMMENT",
    "COLLATE",
    "GENERATED",
    "IDENTITY",
    "AUTO_INCREMENT",
    "CONSTRAINT",
)

YES = "Yes"
NO = "No"
NORMATIVE_STANDARD = "Normative Standard"
GENERAL_STANDARD = "General Standard"
RECOMMENDED_STANDARD = "Recommended Standard"
GENERATED_STATUS = "Generated"
MANUAL_REVIEW_STATUS = "Manual review required"
