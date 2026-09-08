function AgentResponse({ response }) {

  if (!response) {
    return null;
  }

  return (

    <div className="conversation">

      {/* USER MESSAGE */}

      {response.question && (

        <div className="user-message">

          <div className="message-content">

            {response.question}

          </div>

        </div>

      )}


      {/* RESPONSE */}

      <div className="assistant-message">

        <div className="assistant-avatar">

          ✦

        </div>


        <div className="assistant-content">

          <div className="response-text">

            {response.answer}

          </div>


          {response.analysis_result && (

            <details className="analysis-details">

              <summary>

                View analysis

              </summary>

              <pre>

                {JSON.stringify(
                  response.analysis_result,
                  null,
                  2
                )}

              </pre>

            </details>

          )}

        </div>

      </div>

    </div>

  );

}

export default AgentResponse;