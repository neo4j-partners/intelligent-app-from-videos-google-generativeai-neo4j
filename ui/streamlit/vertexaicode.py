"""Wrapper around Google VertexAI Codey models."""
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, root_validator

from langchain.callbacks.manager import CallbackManagerForLLMRun
from langchain.llms.base import LLM
from langchain.llms.utils import enforce_stop_tokens
from langchain.utilities.vertexai import (
    init_vertexai,
    raise_vertex_import_error,
)
from google.cloud import aiplatform
from google.cloud.aiplatform.gapic.schema import predict
from google.protobuf import json_format
from google.protobuf.struct_pb2 import Value

if TYPE_CHECKING:
    from vertexai.language_models._language_models import _LanguageModel


class _VertexAICommon(BaseModel):
    client: "_LanguageModel" = None  #: :meta private:
    model_name: str
    "Model name to use."
    temperature: float = 0.0
    "Sampling temperature, it controls the degree of randomness in token selection."
    max_output_tokens: int = 128
    "Token limit determines the maximum amount of text output from one prompt."
    top_p: float = 0.95
    "Tokens are selected from most probable to least until the sum of their "
    "probabilities equals the top-p value."
    top_k: int = 40
    "How the model selects tokens for output, the next token is selected from "
    "among the top-k most probable tokens."
    stop: Optional[List[str]] = None
    "Optional list of stop words to use when generating."
    # project: Optional[str] = None
    "The default GCP project to use when making Vertex API calls."
    location: str = "us-central1"
    "The default location to use when making API calls."
    credentials: Any = None
    "The default custom credentials (google.auth.credentials.Credentials) to use "
    "when making API calls. If not provided, credentials will be ascertained from "
    "the environment."

    @property
    def _default_params(self) -> Dict[str, Any]:
        base_params = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "top_k": self.top_k,
            "top_p": self.top_p,
        }
        return {**base_params}

    def _predict(
        self, prompt: str, stop: Optional[List[str]] = None, **kwargs: Any
    ) -> str:
        instance_dict = {"prefix": prompt}
        instance = json_format.ParseDict(instance_dict, Value())
        instances = [instance]
        parameters_dict = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "top_k": self.top_k,
            "top_p": self.top_p,
        }
        parameters = json_format.ParseDict(parameters_dict, Value())
        res = self.client.predict(
          endpoint=self.model_name, instances=instances, parameters=parameters
        )
        result = res.predictions[0]["content"].replace('cypher', '')
        # if '```' in res.predictions[0]["content"]:
        #     result = res.predictions[0]["content"].split('```')[1].replace('\n', ' ')
        # else:
        #     result = res.predictions[0]["content"]
        return self._enforce_stop_words(result, stop)

    def _enforce_stop_words(self, text: str, stop: Optional[List[str]] = None) -> str:
        if stop is None and self.stop is not None:
            stop = self.stop
        if stop:
            return enforce_stop_tokens(text, stop)
        return text

    @property
    def _llm_type(self) -> str:
        return "vertexai"

    @classmethod
    def _try_init_vertexai(cls, values: Dict) -> None:
        allowed_params = ["location", "credentials"]
        params = {k: v for k, v in values.items() if k in allowed_params}
        init_vertexai(**params)
        return None


class VertexAICode(_VertexAICommon, LLM):
    """Wrapper around Google Vertex AI large language models."""

    model_name: str = "projects/neo4jbusinessdev/locations/us-central1/publishers/google/models/code-bison@001"
    tuned_model_name: Optional[str] = None
    "The name of a tuned model, if it's provided, model_name is ignored."

    @root_validator()
    def validate_environment(cls, values: Dict) -> Dict:
        """Validate that the python package exists in environment."""
        cls._try_init_vertexai(values)
        try:
            from vertexai.preview.language_models import TextGenerationModel
        except ImportError:
            raise_vertex_import_error()
        client_options = {"api_endpoint": "us-central1-aiplatform.googleapis.com"}
        # Initialize client that will be used to create and send requests.
        # This client only needs to be created once, and can be reused for multiple requests.
        values["client"] = aiplatform.gapic.PredictionServiceClient(
          client_options=client_options
        )
        return values

    def _call(
        self,
        prompt: str,
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> str:
        """Call Vertex model to get predictions based on the prompt.
        Args:
            prompt: The prompt to pass into the model.
            stop: A list of stop words (optional).
            run_manager: A Callbackmanager for LLM run, optional.
        Returns:
            The string generated by the model.
        """
        return self._predict(prompt, stop, **kwargs)