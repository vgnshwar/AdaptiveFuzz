package main

import (
	"context"
	"fmt"
	"log"
	"os"

	"github.com/joho/godotenv"
	"github.com/openai/openai-go"
	"github.com/openai/openai-go/option"
)

func main() {
	if err := godotenv.Load("../.env"); err != nil {
		log.Printf("Warning: Error loading ../.env file: %v", err)
	}

	ctx := context.Background()
	apiKey := os.Getenv("GROQ_API_KEY")
	if apiKey == "" {
		log.Fatal("GROQ_API_KEY not found in environment variables")
	}

	client := openai.NewClient(
		option.WithAPIKey(apiKey),
		option.WithBaseURL("https://api.groq.com/openai/v1"),
	)

	request := openai.ChatCompletionNewParams{
		Model: openai.ChatModel("llama3-8b-8192"),
		Messages: []openai.ChatCompletionMessageParamUnion{
			openai.UserMessage("Hello, how are you?"),
		},
	}

	resp, err := client.Chat.Completions.New(ctx, request)
	if err != nil {
		log.Fatalf("Failed to create chat completion: %v", err)
	}

	fmt.Println(resp.Choices[0].Message.Content)
}
