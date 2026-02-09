from config import MODELS_COMPANIES_MAP
class promptGenerator:    
    def seperated_prompt(self, parts: list[str], model: str):
        """
        生成分离式问题的提示词（MP2模式，包含A和B两个子问题）
        extract函数期望的JSON格式: {{"A_answer": "...", "B_answer": "..."}}
        """
        Problems = ""

        for i, part in enumerate(parts, start=1):
            Problems += f"Problem {i}: {part}\n"
        company = MODELS_COMPANIES_MAP.get(model, "unknown")
        system_role = """You are an expert in Mathematical Problem Solving. Your task is to solve mathematical problems step by step and provide accurate answers."""
        
        user_role = f"""Please solve the following two problems step by step. After your reasoning, provide your final answers in the exact JSON format specified below.

        {Problems}

        IMPORTANT: After completing your step-by-step reasoning, you MUST provide your final answers in the following JSON format (no additional text before or after the JSON):

        {{
            "reasoning": "...",
            "answer_1": "your answer to Problem 1",
            "answer_2": "your answer to Problem 2",
            ...
        }}

        Rules for the final answer:
        1. The JSON must be valid and properly formatted
        2. Put ONLY the answer value in the quotes (no explanations, no units unless part of the answer, no LaTeX formatting)
        3. For numerical answers, provide the exact value
        4. For text answers, provide the exact text
        5. Do not include any reasoning or explanation inside the answer fields
        6. The JSON block should be the last part of your response

        Example format:
        {{
            "reasoning": "...",
            "answer_1": "42",
            "answer_2": "Monday",
        }}"""
        
        if company == "google":
            prompt = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": user_role
                            }
                        ]
                    }
                ]
            }
        elif company == "openai":
            prompt = [
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_role}
            ]
        else:
            raise ValueError(f"Unknown company for model {model}")
        return prompt

    def synthesised_prompt(self, problem: str, model: str):
        """
        生成合成式问题的提示词（完整合成问题）
        extract函数期望的JSON格式: {{"answer": "..."}}
        """
        company = MODELS_COMPANIES_MAP.get(model, "unknown")
        
        system_role = """You are an expert in Mathematical Problem Solving. Your task is to solve mathematical problems step by step and provide accurate answers."""
        
        user_role = f"""Please solve the following problem step by step. After your reasoning, provide your final answer in the exact JSON format specified below.

        Problem: {problem}

        IMPORTANT: After completing your step-by-step reasoning, you MUST provide your final answer in the following JSON format (no additional text before or after the JSON):

        {{  
            "reasoning": "...",
            "answer": "your final answer"
        }}

        Rules for the final answer:
        1. The JSON must be valid and properly formatted
        2. Put ONLY the answer value in the quotes (no explanations, no units unless part of the answer, no LaTeX formatting)
        3. For numerical answers, provide the exact value
        4. For text answers, provide the exact text
        5. Do not include any reasoning or explanation inside the answer field
        6. The JSON block should be the last part of your response
        7. Be clear do not include the delta answer in the final answer. Only provide the final answer.

        Example format:
        {{  
            "reasoning": "...",
            "answer": "42"
        }}

        or

        {{  
            "reasoning": "...",
            "answer": "Monday"
        }}"""
        
        if company == "google":
            prompt = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": user_role
                            }
                        ]
                    }
                ]
            }
        elif company == "openai":
            prompt = [
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_role}
            ]
        else:
            raise ValueError(f"Unknown company for model {model}")
        return prompt

    def judge_prompt(self, answer: list[str], truth: list[str]):
        
        combination = []
        for a, t in zip(answer, truth):
            combination.append({"answer": a, "truth": t})
        system_role = """You are an expert in Mathematical Problem Evaluation. Your task is to carefully compare the given answers with the correct answers and determine if they are equivalent."""
        
        user_role = f"""Please compare the following answers with the correct answers and determine if each answer is correct (equivalent).

        {combination}

        Rules for judgment:
        1. The JSON must be valid and properly formatted
        2. Compare each answer pair carefully - they should be considered correct if they are mathematically or logically equivalent
        3. Ignore minor formatting differences (spaces, capitalization, etc.) unless they affect the meaning
        4. For numerical answers, consider them equivalent if they represent the same value (e.g., "42" and "42.0" are equivalent)
        5. For text answers, consider them equivalent if they convey the same meaning
        6. Return true only if the answers are truly equivalent, false otherwise
        7. The correctness list should have the same length as the number of answer pairs
        8. The JSON block should be the last part of your response
        9. Compare the answers and truths in the order of the combination list and return the correctness list in the same order
        10. Be very careful when you judge the correctness, as there are many ways to express an answer, be sure to consider all possible equivalent expressions.

        Special Cases:
        1. Some answers may include units and some may not. For examples, "7200" is equivalent to "7200\\mathrm{{MB}}", "60" is equivalent to "60 \\%" and etc.
2. Be careful with the unit sign "%", for example, the ground truth "18%" may be directly expressed as "18" without the "%" or other equivalent forms, 18%=0.18=18:100=18/100=9/50, either of which should be judged as "true".
3. Notice that only pay attention to the key part of the answer, as long as the key part is equivalent, the answer is correct. For example, "2019, 1010" is equivalent to "(j,k) = (2019, 1010)".
4. If an answer is approximately equal to the ground truth, for example, "3/4" is approximately equal to "\\frac{{3-3^{{-999}}}}{{4}}”, this kind of answer should be judged as false.



        IMPORTANT: After your analysis, you MUST provide your judgment in the following JSON format (no additional text before or after the JSON):

        {{
            "correctness": [true/false for Answer 1, true/false for Answer 2, ...]
        }}

        Example format (for 1 answer):
        {{
            "correctness": [true]
        }}

        or (for 2 answers):
        {{
            "correctness": [true, false]
        }}"""
        
        prompt = [
            {"role": "system", "content": system_role},
            {"role": "user", "content": user_role}
        ]
        return prompt

def get_prompt_builder():
    return promptGenerator()
